"""Next-item recommender based on BKT mastery and the strict graph.

Idea: pick a small batch of tasks that have *high information gain* — i.e.
where the predicted probability of correctness is in the zone of proximal
development (around 0.6-0.7). Too-easy items waste time; too-hard items
discourage.

Score(task) = sum over linked concepts of:
    weight(task→concept) * info_gain(p_l(concept))
where ``info_gain(p_l)`` is highest near p_correct ≈ 0.6 and tapers toward 0
and 1. We use the canonical entropy of a Bernoulli(p_correct) as the gain.

Filters:
  * skip tasks the user has already answered recently (last ``cooldown_n``
    distinct task_ids)
  * skip tasks whose linked concepts are all already mastered (p_correct >
    0.85)
  * prefer tasks linked to concepts the user has seen at least once
    (slight boost — to ensure we deepen rather than scatter)
"""

from __future__ import annotations

import math
import random
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.exams.bkt import (
    TARGET_RETRIEVABILITY,
    BKTParams,
    MasteryStore,
    predict_correct,
)
from app.exams.graph_service import StrictGraph


@dataclass
class Recommendation:
    task_id: int
    score: float
    expected_p_correct: float
    target_concepts: list[tuple[str, str, float]]  # (concept_id, term, p_l)
    reason: str
    due_score: float = 0.0  # 1 - mean retrievability; 0 if no prior reviews


def _bernoulli_entropy(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log(p) + (1.0 - p) * math.log(1.0 - p))


def _read_recent_task_ids(log_path: Path, user_id: int, last_n: int = 12) -> list[int]:
    if not log_path.exists():
        return []
    seen: list[int] = []
    try:
        # Walk backward; jsonl is small enough for MVP scale.
        for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                row = __import__("json").loads(line)
            except Exception:
                continue
            if int(row.get("user_id", -1)) != user_id:
                continue
            tid = int(row.get("task_id", 0))
            if tid and tid not in seen:
                seen.append(tid)
            if len(seen) >= last_n:
                break
    except OSError:
        return []
    return seen


def _prereq_readiness(
    *,
    concept_ids: list[str],
    graph: StrictGraph,
    store: MasteryStore,
    threshold: float = 0.45,
) -> tuple[float, list[str]]:
    """How ready is a task's concepts in terms of their prerequisites?

    For each prereq concept ``A`` of the task's concepts, look at mastery
    posterior ``p_l(A)``. Returns ``(avg_readiness, weak_prereq_ids)`` where:
      * avg_readiness ∈ [0, 1] — mean ``p_l`` across all prereqs
      * weak_prereq_ids — list of prereqs with ``p_l < threshold``

    If a task has no prereqs in the graph, readiness is 1.0 (no blockers).
    """
    prereqs: set[str] = set()
    for cid in concept_ids:
        for p in graph.prereqs_of.get(cid, []):
            if p not in concept_ids:  # ignore self-dependence within the same task
                prereqs.add(p)
    if not prereqs:
        return 1.0, []
    pls = [store.p_l(p) for p in prereqs]
    avg = sum(pls) / len(pls)
    weak = [p for p in prereqs if store.p_l(p) < threshold]
    return avg, weak


def recommend_next(
    *,
    graph: StrictGraph,
    store: MasteryStore,
    count: int = 5,
    cooldown: int = 12,
    log_path: Path | None = None,
    target_p: float = 0.65,
    rng_seed: int | None = None,
) -> list[Recommendation]:
    """Return ``count`` task ids in a learning-optimal order.

    Scoring layers:
      1. proximity to ``target_p`` (zone of proximal development),
      2. Bernoulli entropy of expected correctness (information gain),
      3. PREREQUISITE readiness penalty — if the task tests concept B but
         a prereq A is barely known (``p_l < 0.45``), the task is heavily
         downscored and surfaced only after A becomes solid.
    """
    recent = set(_read_recent_task_ids(log_path, store.user_id, last_n=cooldown)) if log_path else set()
    params = store.params
    now = _time.time()

    rng = random.Random(rng_seed) if rng_seed is not None else random
    candidates: list[Recommendation] = []
    for n in graph.nodes:
        if n.get("type") != "Task":
            continue
        task_id = int(str(n.get("id", "tk:0")).removeprefix("tk:"))
        if task_id in recent:
            continue
        skills = graph.skills_by_task.get(task_id, [])
        if not skills:
            continue
        # Combine concept-level predictions:
        weight_sum = sum(s.score for s in skills) or 1.0
        weighted_p = 0.0
        target_concepts: list[tuple[str, str, float]] = []
        seen_any = False
        reviewed_concepts = 0
        retrievability_sum = 0.0
        for s in skills:
            p_l = store.p_l(s.concept_id)
            if s.concept_id in store.by_concept:
                seen_any = True
            if s.concept_id in store.last_seen:
                reviewed_concepts += 1
                retrievability_sum += store.retrievability_for(s.concept_id, now)
            p_c = predict_correct(p_l, params)
            weighted_p += (s.score / weight_sum) * p_c
            target_concepts.append((s.concept_id, s.concept_term, round(p_l, 4)))

        # FSRS due signal: average (1 - retrievability) over reviewed concepts.
        # Zero for never-seen tasks (they get scored via proximity/entropy alone).
        if reviewed_concepts:
            avg_r = retrievability_sum / reviewed_concepts
        else:
            avg_r = 1.0  # treat unseen as fully fresh — no review pressure yet
        due_score = max(0.0, 1.0 - avg_r)

        # Prereq readiness — small bonus when prereqs are solid, big penalty
        # when at least one prereq is in the "barely known" zone.
        prereq_readiness, weak_prereqs = _prereq_readiness(
            concept_ids=[s.concept_id for s in skills],
            graph=graph,
            store=store,
        )

        proximity = 1.0 - abs(weighted_p - target_p)
        gain = _bernoulli_entropy(weighted_p)
        # Base: proximity to target + information gain, with FSRS due boost.
        # Weights chosen so spacing dominates when concepts are very stale
        # (avg_r < 0.5) but never overrides hard prereq vetoes.
        score = 0.55 * proximity + 0.25 * gain + 0.2 * due_score
        # Apply prereq penalty: scale (0.6..1.0) so a fully-locked task drops by 40%.
        score *= 0.6 + 0.4 * prereq_readiness
        if len(weak_prereqs) >= 2 and prereq_readiness < 0.35:
            continue
        score += rng.random() * 1e-4
        if seen_any:
            score += 0.05
        # Drop "clearly mastered AND still fresh in memory" tasks (R > target).
        if seen_any and weighted_p > 0.92 and avg_r > TARGET_RETRIEVABILITY:
            continue

        reason = _reason(weighted_p, target_p, seen_any, weak_prereqs, graph, due_score)
        candidates.append(
            Recommendation(
                task_id=task_id,
                score=round(score, 4),
                expected_p_correct=round(weighted_p, 4),
                target_concepts=target_concepts[:3],
                reason=reason,
                due_score=round(due_score, 4),
            )
        )

    candidates.sort(key=lambda x: -x.score)
    return candidates[:count]


def _reason(
    p_c: float,
    target: float,
    seen_any: bool,
    weak_prereqs: list[str] | None = None,
    graph: StrictGraph | None = None,
    due_score: float = 0.0,
) -> str:
    if weak_prereqs and graph:
        term = (graph.concept_info.get(weak_prereqs[0]) or {}).get("term") or weak_prereqs[0]
        return f"сначала укрепить: {term}"
    if due_score >= 0.5:
        return "пора повторить"
    if not seen_any:
        return "новая тема для тебя"
    diff = p_c - target
    if -0.1 <= diff <= 0.1:
        return "оптимальная сложность"
    if diff < -0.1:
        return "слабая зона — закрепляем"
    return "освежить пройденное"
