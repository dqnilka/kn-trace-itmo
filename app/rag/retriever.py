"""Retriever: hybrid graph-grounded + vector search.

Given a failed Assessment node and the BFS expansion result, we:
  1. Build a query string = question text + top-N expansion node texts.
  2. Vector-search GRAPH_CHUNKS, GRAPH_CONCEPTS, MD_CHUNKS independently.
  3. Boost results that already appear in the graph expansion (exact id match)
     using a smooth additive boost in [0, 1) — preserves ranking even after
     the boost is applied (avoids the previous saturation at 1.0).
  4. Deduplicate near-identical md_chunks vs graph_chunks based on text overlap.
  5. Return a unified, sorted RetrievedDoc list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

import numpy as np

from app.core.logging import get_logger
from app.graph.knowledge_graph import ExpansionItem, ExpansionResult, KnowledgeGraph
from app.rag.embeddings import BaseEmbedder
from app.rag.vectorstore import GRAPH_CHUNKS, GRAPH_CONCEPTS, MD_CHUNKS, Hit, VectorStore

if TYPE_CHECKING:
    from app.rag.reranker import BaseReranker

logger = get_logger(__name__)


GRAPH_BOOST = 0.25  # boost factor applied without saturation (see boost_score)
MIN_USEFUL_CONTENT_CHARS = 80  # graph nodes with shorter text+definition are skipped (noise)
DEDUP_TOKEN_OVERLAP_THRESHOLD = 0.7  # md_chunks dropped if Jaccard overlap with any graph_chunk >= this


def boost_score(base: float, boost: float = GRAPH_BOOST) -> float:
    """Smooth additive boost that does NOT saturate at 1.0.

    Formula: boosted = base + boost * (1 - base)
    Properties:
      * Monotonic in `base`: a higher-similarity hit stays ranked above a
        lower-similarity hit even after both are boosted.
      * Bounded: boosted in [base, 1.0).
      * boost(0.6, 0.25) ≈ 0.700; boost(0.95, 0.25) ≈ 0.9625 — different,
        unlike the previous min(s+0.25, 1.0) which collapsed both to 1.0.
    """
    base = max(0.0, min(1.0, base))
    return base + boost * (1.0 - base)


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{3,}")


def _tokens(text: str) -> set[str]:
    """Lower-cased token bag for Jaccard-similarity dedup."""
    return {m.lower() for m in _TOKEN_RE.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / max(1, len(a | b))


@dataclass
class RetrievedDoc:
    node_id: str
    node_type: str  # Chunk | Concept | MdChunk
    text: str
    score: float
    source: str  # 'graph_chunks' | 'graph_concepts' | 'md_chunks'
    metadata: dict
    in_graph_expansion: bool = False
    via_edge_types: tuple[str, ...] = ()
    snippet_max: int = 400

    @property
    def snippet(self) -> str:
        if len(self.text) <= self.snippet_max:
            return self.text
        return self.text[: self.snippet_max] + "…"


class Retriever:
    def __init__(
        self,
        store: VectorStore,
        embedder: BaseEmbedder,
        top_k_graph_chunks: int = 4,
        top_k_concepts: int = 3,
        top_k_md: int = 4,
        reranker: "BaseReranker | None" = None,
        reranker_top_k_out: int = 8,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._top_k_graph_chunks = top_k_graph_chunks
        self._top_k_concepts = top_k_concepts
        self._top_k_md = top_k_md
        self._reranker = reranker
        self._reranker_top_k_out = reranker_top_k_out

    def _build_query_text(
        self,
        question_text: str,
        expansion: ExpansionResult,
        related_limit: int = 6,
    ) -> str:
        parts: list[str] = [question_text.strip()]
        for it in expansion.top(related_limit):
            t = it.node.text
            if it.node.definition:
                t = it.node.definition + ". " + t
            parts.append(t.strip())
        return " | ".join(p for p in parts if p)

    def retrieve(
        self,
        question_text: str,
        expansion: ExpansionResult,
        kg: KnowledgeGraph,
        extra_queries: list[str] | None = None,
    ) -> list[RetrievedDoc]:
        """Retrieve top-K relevant fragments.

        Args:
            extra_queries: optional list of focused mini-queries (e.g. one per
                multiple-choice option). For each, we run a small retrieve
                against md_chunks and graph_chunks (top_k=1-2 each), and merge
                the hits in. This helps when the main query is too noisy to
                pull the precise definition for one of the options.
        """
        query_text = self._build_query_text(question_text, expansion)
        q_vec = self._embedder.encode([query_text], mode="query")[0]

        chunk_hits = self._store.search(GRAPH_CHUNKS, q_vec, top_k=self._top_k_graph_chunks)
        concept_hits = self._store.search(GRAPH_CONCEPTS, q_vec, top_k=self._top_k_concepts)
        md_hits = self._store.search(MD_CHUNKS, q_vec, top_k=self._top_k_md)

        expansion_ids = {it.node.id for it in expansion.items}
        via_map: dict[str, tuple[str, ...]] = {it.node.id: it.via_edge_types for it in expansion.items}

        docs: list[RetrievedDoc] = []
        docs.extend(self._wrap_hits(chunk_hits, "graph_chunks", expansion_ids, via_map))
        docs.extend(self._wrap_hits(concept_hits, "graph_concepts", expansion_ids, via_map))
        docs.extend(self._wrap_hits(md_hits, "md_chunks", expansion_ids, via_map))

        # ---- Mini-retrieve per extra query (e.g. per multiple-choice option) ----
        if extra_queries:
            seen_ids = {d.node_id for d in docs}
            for eq in extra_queries:
                eq = (eq or "").strip()
                if not eq:
                    continue
                ev = self._embedder.encode([eq], mode="query")[0]
                # one extra md hit + one concept hit per option
                for src, k in ((MD_CHUNKS, 1), (GRAPH_CONCEPTS, 1)):
                    extra = self._store.search(src, ev, top_k=k)
                    for h in extra:
                        nid = h.metadata.get("node_id", h.id)
                        if nid in seen_ids:
                            continue
                        if len((h.text or "").strip()) < MIN_USEFUL_CONTENT_CHARS:
                            continue
                        score = h.score
                        if nid in expansion_ids:
                            score = boost_score(score, GRAPH_BOOST)
                        docs.append(
                            RetrievedDoc(
                                node_id=str(nid),
                                node_type=str(h.metadata.get("node_type", "Chunk")),
                                text=h.text,
                                score=float(score),
                                source=src,
                                metadata=dict(h.metadata) | {"matched_option_query": eq[:80]},
                                in_graph_expansion=nid in expansion_ids,
                                via_edge_types=via_map.get(str(nid), ()),
                            )
                        )
                        seen_ids.add(nid)

        # ---- Inject expansion items themselves with synthetic score ----
        # This guarantees concepts/chunks discovered by BFS appear even if their
        # vectors didn't make top-k.
        # Filter: skip nodes with no useful content.
        for it in expansion.top(8):
            n = it.node
            if any(d.node_id == n.id for d in docs):
                continue
            text = n.text or ""
            if n.definition:
                text = (n.definition + ". " + text).strip().rstrip(".")
            if len(text.strip()) < MIN_USEFUL_CONTENT_CHARS:
                continue
            source = "graph_chunks" if n.type == "Chunk" else "graph_concepts"
            # Synthetic score in [0.55, 0.85] derived from BFS path strength.
            synth = 0.55 + min(0.30, it.score * 0.3)
            docs.append(
                RetrievedDoc(
                    node_id=n.id,
                    node_type=n.type,
                    text=text,
                    score=synth,
                    source=source,
                    metadata={"node_id": n.id, "node_type": n.type, "from_graph": True},
                    in_graph_expansion=True,
                    via_edge_types=it.via_edge_types,
                )
            )

        # ---- Deduplicate md_chunks against graph_chunks (text-overlap) ----
        # graph_chunks come from the curated graph; md_chunks are wider but may
        # cover the exact same paragraph. Drop md_chunks that overlap heavily
        # with any already-present graph_chunk.
        graph_token_sets = [
            (d.node_id, _tokens(d.text)) for d in docs if d.source == "graph_chunks"
        ]
        deduped: list[RetrievedDoc] = []
        for d in docs:
            if d.source == "md_chunks" and graph_token_sets:
                d_tokens = _tokens(d.text)
                max_overlap = max(
                    (_jaccard(d_tokens, gt) for _, gt in graph_token_sets),
                    default=0.0,
                )
                if max_overlap >= DEDUP_TOKEN_OVERLAP_THRESHOLD:
                    logger.info(
                        "Dedup: drop %s (overlap=%.2f with a graph_chunk)",
                        d.node_id, max_overlap,
                    )
                    continue
            deduped.append(d)

        deduped.sort(key=lambda d: d.score, reverse=True)

        # ---- Cross-encoder reranking (optional) ----
        if self._reranker is not None:
            # Use the original question (without context appendix) for scoring.
            # The retrieved docs themselves carry the context now; mixing the
            # whole concatenated query into a CE pair would reduce quality.
            ce_query = question_text.strip() or query_text
            before_ids = [d.node_id for d in deduped[:5]]
            deduped = self._reranker.rerank(
                ce_query,
                deduped,
                top_k=self._reranker_top_k_out,
            )
            after_ids = [d.node_id for d in deduped[:5]]
            if before_ids != after_ids:
                logger.info(
                    "Reranker reordered top-5: %s → %s",
                    before_ids, after_ids,
                )

        return deduped

    def _wrap_hits(
        self,
        hits: list[Hit],
        source: str,
        expansion_ids: set,
        via_map: dict[str, tuple[str, ...]],
    ) -> list[RetrievedDoc]:
        out: list[RetrievedDoc] = []
        for h in hits:
            node_id = h.metadata.get("node_id", h.id)
            node_type = h.metadata.get("node_type", "Chunk")
            # Skip low-content hits — they only add noise to LLM context and sources.
            if len((h.text or "").strip()) < MIN_USEFUL_CONTENT_CHARS:
                continue
            score = h.score
            if node_id in expansion_ids:
                score = boost_score(score, GRAPH_BOOST)
            out.append(
                RetrievedDoc(
                    node_id=str(node_id),
                    node_type=str(node_type),
                    text=h.text,
                    score=float(score),
                    source=source,
                    metadata=dict(h.metadata),
                    in_graph_expansion=node_id in expansion_ids,
                    via_edge_types=via_map.get(str(node_id), ()),
                )
            )
        return out
