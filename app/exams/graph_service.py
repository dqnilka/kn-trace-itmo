"""Per-exam strict-graph accessor.

Loads ``data/exams/{slug}/graph.json`` and ``task_skills.jsonl`` into memory
once and exposes lookup tables used by BKT / recommend / explain layers.

The graph schema is described in AS_IS_TO_BE.md §2.4 (Chapter / Theme / Task
/ Concept nodes; HAS_THEME / HAS_TASK / TESTS_CONCEPT / BELONGS_TO_THEME
edges). Anything else (PREREQUISITE etc.) is added by later pipeline steps.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.core.logging import get_logger
from app.exams.registry import Exam

logger = get_logger(__name__)


@dataclass
class TaskSkill:
    """A scored link between a Task and a Concept."""

    task_id: int
    concept_id: str
    concept_term: str
    score: float


@dataclass
class StrictGraph:
    """In-memory view of a per-exam graph.

    All lookups are precomputed at load time; query helpers are pure reads.
    """

    exam_slug: str
    meta: dict
    nodes: list[dict]
    edges: list[dict]
    # Adjacency / lookup tables
    skills_by_task: dict[int, list[TaskSkill]] = field(default_factory=dict)
    tasks_by_concept: dict[str, list[int]] = field(default_factory=dict)
    concepts_by_theme: dict[str, list[str]] = field(default_factory=dict)
    themes_by_chapter: dict[int, list[str]] = field(default_factory=dict)
    chapter_by_theme: dict[str, int] = field(default_factory=dict)
    # PREREQUISITE adjacency: concept_id -> [concept_id requiring it]
    prereqs_of: dict[str, list[str]] = field(default_factory=dict)  # B requires A: prereqs_of[B] = [A,...]
    dependants_of: dict[str, list[str]] = field(default_factory=dict)  # A unlocks B: dependants_of[A] = [B,...]
    # Concept metadata for display / debugging
    concept_info: dict[str, dict] = field(default_factory=dict)

    @property
    def n_tasks(self) -> int:
        return sum(1 for n in self.nodes if n.get("type") == "Task")

    @property
    def n_concepts(self) -> int:
        return sum(1 for n in self.nodes if n.get("type") == "Concept")

    def tested_concepts_for_tasks(
        self, task_ids: Iterable[int], top_k: int = 12
    ) -> list[str]:
        """Concepts ranked by how strongly a set of tasks actually test them.

        Uses the ``TESTS_CONCEPT`` signal (``task_skills.jsonl``) rather than
        ``BELONGS_TO_THEME``: a concept's weight is the sum of its task↔concept
        scores across the given tasks. This is what makes theme theory line up
        with the questions the student will actually see — see
        ``get_theme_article`` and ``theme_summary``.

        Returns concept_ids (without the ``co:`` prefix), highest weight first.
        """
        agg: dict[str, float] = defaultdict(float)
        for tid in task_ids:
            for ts in self.skills_by_task.get(int(tid), []):
                agg[ts.concept_id] += ts.score
        ranked = sorted(agg, key=lambda c: -agg[c])
        return ranked[:top_k] if top_k else ranked


def _load_task_skills(path: Path) -> list[TaskSkill]:
    if not path.exists():
        return []
    out: list[TaskSkill] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        out.append(
            TaskSkill(
                task_id=int(row["task_id"]),
                concept_id=str(row["concept_id"]),
                concept_term=str(row.get("concept_term", "")),
                score=float(row.get("score", 0.0)),
            )
        )
    return out


def load_strict_graph(exam: Exam) -> StrictGraph:
    """Read ``graph.json`` and ``task_skills.jsonl`` from the exam directory."""
    graph_path = exam.root / "graph.json"
    skills_path = exam.root / "task_skills.jsonl"

    if not graph_path.exists():
        logger.warning(
            "Strict graph not found at %s — exam will have no graph layer", graph_path
        )
        return StrictGraph(
            exam_slug=exam.slug, meta={}, nodes=[], edges=[]
        )

    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = list(raw.get("nodes") or [])
    edges = list(raw.get("edges") or [])

    # task_id (int) -> [TaskSkill]
    skills_by_task: dict[int, list[TaskSkill]] = defaultdict(list)
    tasks_by_concept: dict[str, list[int]] = defaultdict(list)
    for ts in _load_task_skills(skills_path):
        skills_by_task[ts.task_id].append(ts)
        tasks_by_concept[ts.concept_id].append(ts.task_id)
    # sort skills by score desc per task
    for ks in skills_by_task.values():
        ks.sort(key=lambda x: -x.score)

    # theme_code -> [concept_id], from BELONGS_TO_THEME edges (preferred)
    # or via skill→task→theme aggregation as fallback.
    concepts_by_theme: dict[str, list[str]] = defaultdict(list)
    prereqs_of: dict[str, list[str]] = defaultdict(list)
    dependants_of: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        et = e.get("type")
        if et == "BELONGS_TO_THEME":
            cid = _strip_prefix(e.get("source"), "co:")
            tcode = _strip_prefix(e.get("target"), "th:")
            if cid and tcode:
                concepts_by_theme[tcode].append(cid)
        elif et == "PREREQUISITE":
            f = _strip_prefix(e.get("source"), "co:")
            t = _strip_prefix(e.get("target"), "co:")
            if f and t:
                prereqs_of[t].append(f)       # t depends on f
                dependants_of[f].append(t)     # f unlocks t

    # chapter_id -> [theme_code], theme_code -> chapter_id
    themes_by_chapter: dict[int, list[str]] = defaultdict(list)
    chapter_by_theme: dict[str, int] = {}
    for n in nodes:
        if n.get("type") == "Theme":
            code = str(n.get("code"))
            chid = int(n.get("chapter_id") or 0)
            chapter_by_theme[code] = chid
            themes_by_chapter[chid].append(code)

    # Concept lookup
    concept_info: dict[str, dict] = {}
    for n in nodes:
        if n.get("type") == "Concept":
            cid = _strip_prefix(n.get("id", ""), "co:")
            concept_info[cid] = {
                "id": cid,
                "term": n.get("term"),
                "definition": n.get("definition"),
                "aliases": n.get("aliases") or [],
            }

    g = StrictGraph(
        exam_slug=exam.slug,
        meta=raw.get("_meta", {}),
        nodes=nodes,
        edges=edges,
        skills_by_task=dict(skills_by_task),
        tasks_by_concept=dict(tasks_by_concept),
        concepts_by_theme=dict(concepts_by_theme),
        themes_by_chapter=dict(themes_by_chapter),
        chapter_by_theme=chapter_by_theme,
        prereqs_of=dict(prereqs_of),
        dependants_of=dict(dependants_of),
        concept_info=concept_info,
    )
    logger.info(
        "Loaded strict graph for %s: %d nodes, %d edges, %d task↔concept links, %d prereq edges",
        exam.slug, len(nodes), len(edges),
        sum(len(v) for v in skills_by_task.values()),
        sum(len(v) for v in prereqs_of.values()),
    )
    return g


def _strip_prefix(s: str | None, prefix: str) -> str:
    if not s:
        return ""
    return s[len(prefix):] if s.startswith(prefix) else s


class GraphRegistry:
    """Caches StrictGraph per exam slug."""

    def __init__(self) -> None:
        self._cache: dict[str, StrictGraph] = {}

    def get(self, exam: Exam) -> StrictGraph:
        if exam.slug not in self._cache:
            self._cache[exam.slug] = load_strict_graph(exam)
        return self._cache[exam.slug]

    def invalidate(self, slug: str) -> None:
        self._cache.pop(slug, None)

    def all(self) -> Iterable[StrictGraph]:
        return self._cache.values()
