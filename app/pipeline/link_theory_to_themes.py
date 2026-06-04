"""Precompute Theme ↔ MD-section mapping.

For each theme of the exam bank, we want to know which slices of the textbook
(``md_chunks`` collection in Chroma, already populated by ``app.rag.ingest``)
are most relevant. The mapping is used by:

  * ``/api/v1/exams/{slug}/explain`` — to prioritise theme-scoped chunks
    instead of searching the whole textbook every time;
  * a future ``GET /exams/{slug}/theme/{code}`` endpoint — to render a quick
    "theory by theme" article from the top sections.

Approach (no extra LLM calls):
  1. For each theme, build a query string out of:
       - theme.name
       - chapter.name
       - top-K concept terms the theme's tasks actually test (TESTS_CONCEPT,
         ranked by edge weight; BELONGS_TO_THEME as fallback)
  2. Embed the query with E5 (same embedder as the API).
  3. Cosine-rank the existing ``md_chunks`` collection (already L2-normalised).
  4. Keep top-N hits per theme with score ≥ ``min_score``.

Output: ``data/exams/{slug}/theme_sections.json``::

    {
      "_meta": {...},
      "by_theme": {
        "1.1": [
          {"chunk_id": "...", "section_path": "...",
           "char_offset": 1234, "char_length": 800,
           "snippet": "...", "score": 0.78},
          ...
        ]
      }
    }
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.core.logging import get_logger
from app.rag.embeddings import BaseEmbedder
from app.rag.vectorstore import MD_CHUNKS, VectorStore

logger = get_logger(__name__)


@dataclass
class ThemeSectionLink:
    theme_code: str
    chunk_id: str
    section_path: str
    char_offset: int
    char_length: int
    snippet: str
    score: float


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=1 if x.ndim > 1 else 0, keepdims=True)
    if isinstance(norm, np.ndarray):
        norm[norm == 0] = 1.0
    elif norm == 0:
        norm = 1.0
    return x / norm


def _theme_query(
    theme: dict,
    chapter: dict | None,
    concept_terms: list[str],
) -> str:
    parts: list[str] = []
    if chapter and chapter.get("name"):
        parts.append(str(chapter["name"]))
    parts.append(str(theme.get("name") or theme.get("code") or ""))
    if concept_terms:
        # Concepts give us strong topical signal — short comma-joined head is enough.
        parts.append(", ".join(concept_terms[:12]))
    return " — ".join(p for p in parts if p)


def link_theory_to_themes(
    *,
    graph: dict,
    bank: dict,
    embedder: BaseEmbedder,
    store: VectorStore,
    top_n: int = 6,
    min_score: float = 0.35,
) -> tuple[list[ThemeSectionLink], dict[str, Any]]:
    """Compute theme→MD-section ranking by cosine similarity in ``md_chunks``."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    chapters_by_id: dict[int, dict] = {}
    themes_by_code: dict[str, dict] = {}
    concept_term_by_id: dict[str, str] = {}
    for n in nodes:
        if n.get("type") == "Chapter":
            chapters_by_id[int(n.get("num") or 0)] = n
        elif n.get("type") == "Theme":
            themes_by_code[str(n.get("code"))] = n
        elif n.get("type") == "Concept":
            cid = str(n.get("id", "")).removeprefix("co:")
            concept_term_by_id[cid] = str(n.get("term") or cid)

    # Theme → ranked concept terms. Primary signal is TESTS_CONCEPT: the
    # concepts the theme's TASKS actually probe (aggregated by edge weight),
    # so the textbook query — and therefore the retrieved theory — lines up
    # with the questions the student will see. BELONGS_TO_THEME is kept only as
    # a fallback for themes whose tasks have no concept links yet.
    task_theme: dict[str, str] = {}
    for n in nodes:
        if n.get("type") == "Task":
            tk = str(n.get("id", ""))
            tcode = str(n.get("theme_code") or "")
            if tk and tcode:
                task_theme[tk] = tcode

    tested_weight: dict[str, dict[str, float]] = {}
    belongs_terms: dict[str, list[str]] = {}
    for e in edges:
        et = e.get("type")
        if et == "TESTS_CONCEPT":
            tk = str(e.get("source") or "")
            cid = str(e.get("target") or "").removeprefix("co:")
            tcode = task_theme.get(tk)
            if not tcode or not cid:
                continue
            w = float(e.get("weight") or 1.0)
            tested_weight.setdefault(tcode, {})
            tested_weight[tcode][cid] = tested_weight[tcode].get(cid, 0.0) + w
        elif et == "BELONGS_TO_THEME":
            cid = str(e.get("source") or "").removeprefix("co:")
            tcode = str(e.get("target") or "").removeprefix("th:")
            term = concept_term_by_id.get(cid)
            if cid and tcode and term:
                belongs_terms.setdefault(tcode, []).append(term)

    concepts_by_theme: dict[str, list[str]] = {}
    for tcode, weights in tested_weight.items():
        ranked = sorted(weights, key=lambda c: -weights[c])
        terms = [concept_term_by_id[c] for c in ranked if c in concept_term_by_id]
        if terms:
            concepts_by_theme[tcode] = terms
    # Fallback for themes without task→concept signal.
    for tcode, terms in belongs_terms.items():
        concepts_by_theme.setdefault(tcode, terms)

    themes = bank.get("themes") or []
    if not themes:
        logger.warning("Bank has no themes — nothing to link")
        return [], {}

    if store.count(MD_CHUNKS) == 0:
        logger.warning("md_chunks collection is empty — run ingest first")
        return [], {}

    started = time.time()
    out: list[ThemeSectionLink] = []
    seen_chunks_per_theme: dict[str, set[str]] = {}

    for theme in themes:
        tcode = str(theme.get("code"))
        chap = None
        cid = theme.get("chapter_id")
        if cid is not None:
            chap = chapters_by_id.get(int(cid))
        terms = concepts_by_theme.get(tcode, [])
        query = _theme_query(theme, chap, terms)
        if not query.strip():
            continue
        q_emb = embedder.encode([query], mode="query")[0]
        hits = store.search(MD_CHUNKS, q_emb, top_k=max(top_n * 2, 8))
        seen = seen_chunks_per_theme.setdefault(tcode, set())
        kept = 0
        for h in hits:
            if h.score < min_score:
                continue
            if h.id in seen:
                continue
            seen.add(h.id)
            meta = h.metadata or {}
            out.append(
                ThemeSectionLink(
                    theme_code=tcode,
                    chunk_id=h.id,
                    section_path=str(meta.get("section_path", "")),
                    char_offset=int(meta.get("char_offset", 0) or 0),
                    char_length=int(meta.get("char_length", 0) or 0),
                    snippet=(h.text or "").strip()[:280],
                    score=round(float(h.score), 4),
                )
            )
            kept += 1
            if kept >= top_n:
                break
        logger.debug("Theme %s: %d top sections (query=%r)", tcode, kept, query[:60])

    elapsed = round(time.time() - started, 1)
    meta = {
        "generated_in_seconds": elapsed,
        "themes_covered": len({l.theme_code for l in out}),
        "total_links": len(out),
        "top_n": top_n,
        "min_score": min_score,
    }
    logger.info(
        "theme→section linking: %d links across %d themes in %ss",
        len(out), meta["themes_covered"], elapsed,
    )
    return out, meta


def save_theme_sections(
    links: list[ThemeSectionLink],
    path: Path,
    meta: dict[str, Any],
) -> None:
    by_theme: dict[str, list[dict]] = {}
    for l in links:
        by_theme.setdefault(l.theme_code, []).append(
            {
                "chunk_id": l.chunk_id,
                "section_path": l.section_path,
                "char_offset": l.char_offset,
                "char_length": l.char_length,
                "snippet": l.snippet,
                "score": l.score,
            }
        )
    payload = {"_meta": meta, "by_theme": by_theme}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
