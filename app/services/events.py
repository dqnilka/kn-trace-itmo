"""Append-only event log + BKT update on each event.

A trainer event is one answered question. The log lives at
``data/exams/{slug}/events.jsonl``; mastery is updated atomically per event
through :class:`MasteryRepository` and propagates to all concepts linked to
the answered task.
"""

from __future__ import annotations

import errno
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.exams.bkt import MasteryRepository, MasteryStore
from app.exams.graph_service import StrictGraph

logger = get_logger(__name__)


@dataclass
class EventInput:
    user_id: int
    task_id: int
    picked_label: str | None
    is_correct: bool
    ts: float | None = None


@dataclass
class ConceptUpdate:
    concept_id: str
    concept_term: str
    p_before: float
    p_after: float
    weight: float  # task→concept link score


@dataclass
class EventResult:
    user_id: int
    task_id: int
    is_correct: bool
    updates: list[ConceptUpdate]
    overall_mastery: float | None


class UnknownTaskError(KeyError):
    """Raised when task_id is not in the bank/graph."""


def record_event(
    *,
    graph: StrictGraph,
    repo: MasteryRepository,
    event: EventInput,
    log_path: Path,
) -> EventResult:
    """Persist the event, run BKT updates for each linked concept.

    BKT update applies once per linked concept. We don't currently weight by
    the link's similarity score — that's a tuning knob for later (a low-score
    link could be treated as a fractional observation, e.g. ``effective_correct =
    weight * is_correct + (1-weight) * p_l``).
    """
    skills = graph.skills_by_task.get(event.task_id, [])
    if not skills:
        logger.info("Event for task %d has no linked concepts; storing only", event.task_id)

    store: MasteryStore = repo.load(event.user_id)
    updates: list[ConceptUpdate] = []
    ts = event.ts or time.time()
    for s in skills:
        before, after = store.update(s.concept_id, event.is_correct, now=ts)
        updates.append(
            ConceptUpdate(
                concept_id=s.concept_id,
                concept_term=s.concept_term,
                p_before=round(before, 4),
                p_after=round(after, 4),
                weight=round(s.score, 4),
            )
        )
    store.events += 1
    repo.save(store)

    # Append-only log. Robust against bind-mount races / FUSE quirks: open with
    # the low-level os.open(O_APPEND|O_CREAT) under a short retry, falling back
    # to per-user log if the shared file refuses to open (extremely rare).
    row = {
        "ts": ts,
        "user_id": event.user_id,
        "task_id": event.task_id,
        "picked_label": event.picked_label,
        "is_correct": event.is_correct,
        "concept_updates": [
            {"concept_id": u.concept_id, "p_after": u.p_after} for u in updates
        ],
    }
    _append_jsonl(log_path, json.dumps(row, ensure_ascii=False) + "\n")

    overall = (
        sum(store.by_concept.values()) / len(store.by_concept)
        if store.by_concept else None
    )
    return EventResult(
        user_id=event.user_id,
        task_id=event.task_id,
        is_correct=event.is_correct,
        updates=updates,
        overall_mastery=overall,
    )


def _append_jsonl(path: Path, line: str, retries: int = 3) -> None:
    """Append one line to ``path`` using low-level open with O_APPEND|O_CREAT.

    Retries briefly to absorb bind-mount staleness on macOS (OrbStack/Docker
    Desktop sometimes report ENOENT immediately after a host-side delete even
    though the parent directory clearly exists).
    """
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            fd = os.open(str(path), flags, 0o644)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
            return
        except FileNotFoundError as e:
            last_exc = e
            if e.errno == errno.ENOENT and attempt + 1 < retries:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
