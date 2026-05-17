"""Bayesian Knowledge Tracing — per-skill posterior mastery.

Classic 4-parameter BKT (Corbett & Anderson 1995):
    P(L_0) — prior probability the student knows the skill
    P(T)   — transition: P(unknown→known) after an attempt
    P(G)   — guess: P(correct | not known)
    P(S)   — slip:  P(incorrect | known)

After observing a correct (c=1) or incorrect (c=0) answer:
    p_eval = P(L_t)
    P(L_t | c=1) = p_eval * (1 - P(S)) / (p_eval * (1 - P(S)) + (1 - p_eval) * P(G))
    P(L_t | c=0) = p_eval * P(S) / (p_eval * P(S) + (1 - p_eval) * (1 - P(G)))
    P(L_{t+1})  = P(L_t | c) + (1 - P(L_t | c)) * P(T)

MVP: globally shared parameters (no per-skill EM fit yet). Later, an offline
fitter (``pipeline/fit_bkt.py``) can produce per-concept dicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BKTParams:
    p_l0: float = 0.30
    p_t: float = 0.10
    p_g: float = 0.20
    p_s: float = 0.10

    @classmethod
    def default(cls) -> "BKTParams":
        return cls()


def update_posterior(p_l: float, is_correct: bool, params: BKTParams) -> float:
    """Bayesian update of P(L) given an observation."""
    p_l = max(min(p_l, 1.0 - 1e-6), 1e-6)
    if is_correct:
        numer = p_l * (1.0 - params.p_s)
        denom = numer + (1.0 - p_l) * params.p_g
    else:
        numer = p_l * params.p_s
        denom = numer + (1.0 - p_l) * (1.0 - params.p_g)
    if denom <= 0:
        return p_l
    p_eval = numer / denom
    # Transition: chance of learning the skill between attempts.
    return p_eval + (1.0 - p_eval) * params.p_t


def predict_correct(p_l: float, params: BKTParams) -> float:
    """P(correct on next attempt) given current mastery."""
    p_l = max(min(p_l, 1.0), 0.0)
    return p_l * (1.0 - params.p_s) + (1.0 - p_l) * params.p_g


# --- FSRS-lite (free spaced repetition scheduler, simplified) ---
#
# We track per-concept memory state alongside BKT posterior:
#   * stability   — current "memory half-life" in seconds (how long until
#                    retrievability falls to ~0.9). Grows on success, shrinks
#                    on failure.
#   * last_seen   — unix timestamp of last review (event).
# Retrievability at time ``t`` is approximated as ``exp(-Δt / S)``. When R
# drops into the 0.7-0.9 band the concept is "ripe for review" — that's the
# zone where recall practice is most effective.
#
# Full FSRS has 17 parameters; we use a simplified 3-knob version:
#   * INITIAL_STABILITY_CORRECT  — S after a first correct (1 day)
#   * INITIAL_STABILITY_WRONG    — S after a first wrong   (1 hour)
#   * EASE_FACTOR                — multiplier on stability for correct reviews
#   * LAPSE_FACTOR               — multiplier for incorrect reviews

INITIAL_STABILITY_CORRECT = 86_400.0   # 1 day
INITIAL_STABILITY_WRONG = 3_600.0      # 1 hour
EASE_FACTOR_BASE = 1.7
LAPSE_FACTOR = 0.4
TARGET_RETRIEVABILITY = 0.85  # spacing target — review when R drops to this


def _next_stability(prev_stability: float, retrievability: float, is_correct: bool) -> float:
    """Update memory stability after a review.

    Approximates FSRS's `S_new = S_prev * f(retrievability, grade)`. Higher
    retrievability at time of review → smaller boost (you already remembered
    well, less learning happened). Failures shrink stability.
    """
    if prev_stability <= 0:
        return INITIAL_STABILITY_CORRECT if is_correct else INITIAL_STABILITY_WRONG
    if is_correct:
        # FSRS-style: easier reviews give less boost. retrievability ~1 → x1, ~0.5 → x2.5.
        factor = EASE_FACTOR_BASE - (retrievability - 0.5)
        return prev_stability * max(1.0, factor)
    # Lapse: cut stability hard but never below the initial-wrong floor.
    return max(INITIAL_STABILITY_WRONG, prev_stability * LAPSE_FACTOR)


def retrievability(stability: float, last_seen: float, now: float) -> float:
    """``R(t) = exp(-(now - last_seen) / stability)`` clamped to [0, 1]."""
    if stability <= 0 or last_seen <= 0:
        return 1.0
    dt = max(0.0, now - last_seen)
    import math
    return float(max(0.0, min(1.0, math.exp(-dt / stability))))


@dataclass
class MasteryStore:
    """User mastery for one exam, persisted as a single JSON file.

    Layout::
        {
          "user_id": 12345,
          "exam_slug": "fsfr-basic",
          "params": {...},
          "by_concept": {"concept_id": p_l, ...},
          "last_seen": {"concept_id": unix_ts, ...},
          "stability": {"concept_id": seconds, ...},
          "events": int
        }
    """

    user_id: int
    exam_slug: str
    params: BKTParams = field(default_factory=BKTParams.default)
    by_concept: dict[str, float] = field(default_factory=dict)
    last_seen: dict[str, float] = field(default_factory=dict)
    stability: dict[str, float] = field(default_factory=dict)
    events: int = 0

    def p_l(self, concept_id: str) -> float:
        return self.by_concept.get(concept_id, self.params.p_l0)

    def stability_for(self, concept_id: str) -> float:
        return self.stability.get(concept_id, 0.0)

    def retrievability_for(self, concept_id: str, now: float) -> float:
        s = self.stability.get(concept_id, 0.0)
        t = self.last_seen.get(concept_id, 0.0)
        return retrievability(s, t, now)

    def update(self, concept_id: str, is_correct: bool, now: float | None = None) -> tuple[float, float]:
        """Bayesian update of P(L) and FSRS update of (stability, last_seen)."""
        before = self.p_l(concept_id)
        after = update_posterior(before, is_correct, self.params)
        self.by_concept[concept_id] = after
        # FSRS spacing
        import time as _time
        ts = now if now is not None else _time.time()
        prev_s = self.stability.get(concept_id, 0.0)
        r_now = self.retrievability_for(concept_id, ts)
        self.stability[concept_id] = _next_stability(prev_s, r_now, is_correct)
        self.last_seen[concept_id] = ts
        return before, after

    def reset(self) -> None:
        self.by_concept.clear()
        self.last_seen.clear()
        self.stability.clear()
        self.events = 0

    def to_json(self) -> dict:
        return {
            "user_id": self.user_id,
            "exam_slug": self.exam_slug,
            "params": {
                "p_l0": self.params.p_l0,
                "p_t": self.params.p_t,
                "p_g": self.params.p_g,
                "p_s": self.params.p_s,
            },
            "by_concept": self.by_concept,
            "last_seen": self.last_seen,
            "stability": self.stability,
            "events": self.events,
        }

    @classmethod
    def from_json(cls, data: dict) -> "MasteryStore":
        p = data.get("params") or {}
        params = BKTParams(
            p_l0=float(p.get("p_l0", 0.30)),
            p_t=float(p.get("p_t", 0.10)),
            p_g=float(p.get("p_g", 0.20)),
            p_s=float(p.get("p_s", 0.10)),
        )
        return cls(
            user_id=int(data["user_id"]),
            exam_slug=str(data["exam_slug"]),
            params=params,
            by_concept=dict(data.get("by_concept") or {}),
            last_seen={k: float(v) for k, v in (data.get("last_seen") or {}).items()},
            stability={k: float(v) for k, v in (data.get("stability") or {}).items()},
            events=int(data.get("events", 0)),
        )


class MasteryRepository:
    """File-backed store for per-user mastery within one exam.

    Each user is one JSON file under ``data/exams/{slug}/users/{user_id}.json``.
    The file is rewritten atomically after every event (single-process MVP).
    For higher throughput / multi-process — replace with sqlite later.
    """

    def __init__(self, exam_root: Path, exam_slug: str) -> None:
        self.exam_root = exam_root
        self.exam_slug = exam_slug
        self.users_dir = exam_root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.users_dir / f"{user_id}.json"

    def load(self, user_id: int) -> MasteryStore:
        p = self._path(user_id)
        if not p.exists():
            return MasteryStore(user_id=user_id, exam_slug=self.exam_slug)
        try:
            return MasteryStore.from_json(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            logger.warning("Mastery for user %d unreadable, resetting: %s", user_id, e)
            return MasteryStore(user_id=user_id, exam_slug=self.exam_slug)

    def save(self, store: MasteryStore) -> None:
        p = self._path(store.user_id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(store.to_json(), ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)


@dataclass
class MasteryAggregate:
    """Roll-up of mastery from concepts → themes → chapters."""

    by_concept: dict[str, float]
    by_theme: dict[str, float]
    by_chapter: dict[int, float]
    overall: float | None


def aggregate_mastery(
    store: MasteryStore,
    concepts_by_theme: dict[str, list[str]],
    themes_by_chapter: dict[int, list[str]],
) -> MasteryAggregate:
    """Aggregate concept-level posterior up the chapter→theme→concept tree.

    Each level is the mean of its children's posterior. Unseen concepts default
    to P_L0 (the prior), so themes with no observed concepts show as the prior.
    """
    by_concept = dict(store.by_concept)

    by_theme: dict[str, float] = {}
    for theme_code, concept_ids in concepts_by_theme.items():
        if not concept_ids:
            continue
        vals = [store.p_l(c) for c in concept_ids]
        by_theme[theme_code] = sum(vals) / len(vals)

    by_chapter: dict[int, float] = {}
    for chap_id, theme_codes in themes_by_chapter.items():
        vals = [by_theme[c] for c in theme_codes if c in by_theme]
        if vals:
            by_chapter[chap_id] = sum(vals) / len(vals)

    overall = (
        sum(by_concept.values()) / len(by_concept) if by_concept else None
    )

    return MasteryAggregate(
        by_concept=by_concept,
        by_theme=by_theme,
        by_chapter=by_chapter,
        overall=overall,
    )
