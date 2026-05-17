"""Link bank tasks to concepts from ``ConceptDictionary.json`` by embedding
similarity.

Each task is represented as ``task_text + правильный ответ + название темы``.
Each concept is represented as ``primary_term + aliases + definition``.
Both go through the same E5 embedder; top-K concepts by cosine similarity are
recorded as candidate ``TESTS_CONCEPT`` edges with a confidence score.

If ``--llm-rerank`` is given (later), the same module re-ranks the top-K
candidates by asking the LLM "which of these concepts is actually tested in
this task?" — that's a separate step kept out of MVP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from app.core.logging import get_logger
from app.rag.embeddings import BaseEmbedder

logger = get_logger(__name__)


@dataclass
class TaskConceptLink:
    task_id: int
    concept_id: str
    concept_term: str
    score: float


def _task_query(task: dict, theme_name: str | None) -> str:
    parts: list[str] = []
    if theme_name:
        parts.append(theme_name)
    parts.append((task.get("task_text") or "").strip())
    correct = next((o for o in task.get("options", []) if o.get("is_correct")), None)
    if correct:
        parts.append((correct.get("text") or "").strip())
    return "\n".join(p for p in parts if p)


def _concept_passage(concept: dict) -> str:
    term = (concept.get("term") or {}) if isinstance(concept.get("term"), dict) else {}
    primary = (term.get("primary") or concept.get("term_primary") or "").strip()
    aliases = term.get("aliases") or []
    definition = (concept.get("definition") or "").strip()
    head = primary
    if aliases:
        head = f"{primary} ({', '.join(aliases)})"
    return f"{head}. {definition}".strip(". ")


def link_tasks_to_concepts(
    *,
    tasks: list[dict],
    themes_by_code: dict[str, dict],
    concepts: list[dict],
    embedder: BaseEmbedder,
    top_k: int = 3,
    min_score: float = 0.35,
    batch: int = 128,
) -> list[TaskConceptLink]:
    """Compute task→concept links by embedding similarity.

    Returns one or more ``TaskConceptLink`` per task (up to ``top_k``), filtered
    by a minimum cosine similarity.
    """
    if not concepts:
        return []
    concept_ids = [c.get("concept_id") or c.get("id") or "" for c in concepts]
    concept_texts = [_concept_passage(c) for c in concepts]
    concept_terms = [
        (c.get("term", {}).get("primary") if isinstance(c.get("term"), dict) else "")
        or ""
        for c in concepts
    ]

    logger.info("Embedding %d concepts...", len(concept_texts))
    concept_emb = embedder.encode(concept_texts, mode="passage")
    # ensure L2-normalized so dot product == cosine similarity
    concept_emb = _l2_normalize(concept_emb)

    out: list[TaskConceptLink] = []
    logger.info("Embedding %d tasks (batch=%d)...", len(tasks), batch)
    for start in range(0, len(tasks), batch):
        chunk = tasks[start : start + batch]
        queries = [_task_query(t, (themes_by_code.get(t.get("theme_code")) or {}).get("name")) for t in chunk]
        q_emb = embedder.encode(queries, mode="query")
        q_emb = _l2_normalize(q_emb)
        # cosine matrix: (n_tasks_in_batch, n_concepts)
        sims = q_emb @ concept_emb.T
        for i, task in enumerate(chunk):
            row = sims[i]
            idxs = np.argsort(-row)[:top_k]
            for j in idxs:
                s = float(row[j])
                if s < min_score:
                    continue
                out.append(
                    TaskConceptLink(
                        task_id=int(task["id"]),
                        concept_id=str(concept_ids[j]),
                        concept_term=str(concept_terms[j]),
                        score=round(s, 4),
                    )
                )
        logger.info(
            "Linked tasks %d..%d / %d", start, start + len(chunk), len(tasks)
        )
    return out


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return x / norm


def save_links_jsonl(links: Iterable[TaskConceptLink], path: Path) -> int:
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for l in links:
            f.write(
                json.dumps(
                    {
                        "task_id": l.task_id,
                        "concept_id": l.concept_id,
                        "concept_term": l.concept_term,
                        "score": l.score,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n += 1
    return n
