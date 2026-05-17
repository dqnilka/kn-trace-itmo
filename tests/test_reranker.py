"""Tests for reranker abstractions and integration with Retriever."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.graph.knowledge_graph import KnowledgeGraph
from app.rag.embeddings import DeterministicHashEmbedder
from app.rag.reranker import (
    BaseReranker,
    CrossEncoderReranker,
    IdentityReranker,
    MockReranker,
)
from app.rag.retriever import RetrievedDoc, Retriever
from app.rag.vectorstore import GRAPH_CHUNKS, GRAPH_CONCEPTS, VectorStore


def _make_doc(node_id: str, text: str, score: float = 0.5) -> RetrievedDoc:
    return RetrievedDoc(
        node_id=node_id,
        node_type="Chunk",
        text=text,
        score=score,
        source="graph_chunks",
        metadata={"node_id": node_id},
    )


# ---------- IdentityReranker ----------


def test_identity_reranker_preserves_order_and_truncates() -> None:
    docs = [_make_doc(f"d{i}", f"text {i}", score=1.0 - i * 0.1) for i in range(5)]
    out = IdentityReranker().rerank("any query", docs, top_k=3)
    assert [d.node_id for d in out] == ["d0", "d1", "d2"]


# ---------- MockReranker (token-overlap, deterministic) ----------


def test_mock_reranker_promotes_token_overlap_match() -> None:
    """MockReranker prefers docs that share tokens with the query, regardless
    of their original retrieval score."""
    docs = [
        # Original retrieval thinks this is the top hit (score 0.95) but
        # it has zero overlap with the query — should be demoted.
        _make_doc("d_top", "Совершенно нерелевантный текст.", score=0.95),
        # Lower retrieval score but full overlap → should bubble up.
        _make_doc("d_match", "Облигация — долговая ценная бумага.", score=0.30),
        _make_doc("d_partial", "Купонная облигация.", score=0.50),
    ]
    out = MockReranker().rerank("Что такое облигация долговая?", docs)
    assert out[0].node_id == "d_match"
    # 'd_top' must lose; either at the bottom or definitely not first
    assert out[0].node_id != "d_top"


def test_mock_reranker_top_k_truncation() -> None:
    docs = [_make_doc(f"d{i}", "Облигация" * (i + 1), score=0.5) for i in range(5)]
    out = MockReranker().rerank("Облигация", docs, top_k=2)
    assert len(out) == 2


# ---------- CrossEncoderReranker (interface only, no model load) ----------


def test_crossencoder_reranker_minmax_normalizer() -> None:
    norm = CrossEncoderReranker._minmax_norm([1.0, 2.0, 3.0])
    assert norm == [0.0, 0.5, 1.0]
    # Constant input: all 0.5
    norm2 = CrossEncoderReranker._minmax_norm([7.0, 7.0, 7.0])
    assert norm2 == [0.5, 0.5, 0.5]
    # Empty
    assert CrossEncoderReranker._minmax_norm([]) == []


def test_crossencoder_reranker_blends_scores_correctly() -> None:
    """Build a fake CE that returns hardcoded scores; verify the blending logic
    without loading a real model."""
    ce = CrossEncoderReranker.__new__(CrossEncoderReranker)
    ce._model_name = "fake"  # type: ignore[attr-defined]
    ce._batch = 32  # type: ignore[attr-defined]
    ce._blend = 0.7  # type: ignore[attr-defined]

    class FakeModel:
        def predict(self, pairs, batch_size=32, show_progress_bar=False):
            # Return CE scores: doc B should win
            mapping = {"A": 1.0, "B": 5.0, "C": 3.0}
            return [mapping[d_text[-1]] for _, d_text in pairs]

    ce._model = FakeModel()  # type: ignore[attr-defined]

    docs = [
        _make_doc("d1", "doc A", score=0.9),  # high retrieval, low CE
        _make_doc("d2", "doc B", score=0.5),  # mid retrieval, high CE
        _make_doc("d3", "doc C", score=0.7),  # mid retrieval, mid CE
    ]
    out = ce.rerank("query", docs)
    # d2 should win with blend=0.7 favoring CE.
    assert out[0].node_id == "d2"
    # Metadata records both raw CE and old retrieval score.
    assert "ce_score" in out[0].metadata
    assert "score_before_rerank" in out[0].metadata


def test_crossencoder_reranker_empty_input() -> None:
    ce = CrossEncoderReranker.__new__(CrossEncoderReranker)
    ce._model_name = "fake"  # type: ignore[attr-defined]
    ce._batch = 32  # type: ignore[attr-defined]
    ce._blend = 0.7  # type: ignore[attr-defined]
    ce._model = None  # type: ignore[attr-defined]
    assert ce.rerank("query", []) == []
    assert ce.rerank("", [_make_doc("d", "x")]) == [_make_doc("d", "x")]


# ---------- Integration: Retriever + MockReranker ----------


def test_retriever_with_reranker_reorders_results(
    tmp_path: Path, kg: KnowledgeGraph
) -> None:
    """When a reranker is wired in, retrieve() returns rerank-ordered docs."""
    embedder = DeterministicHashEmbedder(dim=128)
    store = VectorStore(persist_dir=tmp_path / "chroma_rr")

    chunks = kg.chunks()
    chunk_texts = [
        (n.definition + ". " + n.text) if n.definition else n.text for n in chunks
    ]
    chunk_embs = embedder.encode(chunk_texts, mode="passage")
    store.add_batch(
        GRAPH_CHUNKS,
        [n.id for n in chunks],
        chunk_embs,
        chunk_texts,
        [{"node_id": n.id, "node_type": "Chunk"} for n in chunks],
    )
    concepts = kg.concepts()
    concept_texts = [n.text + ". " + n.definition for n in concepts]
    concept_embs = embedder.encode(concept_texts, mode="passage")
    store.add_batch(
        GRAPH_CONCEPTS,
        [n.id for n in concepts],
        concept_embs,
        concept_texts,
        [{"node_id": n.id, "node_type": "Concept"} for n in concepts],
    )

    retriever_no_rr = Retriever(store=store, embedder=embedder)
    retriever_rr = Retriever(
        store=store,
        embedder=embedder,
        reranker=MockReranker(),
        reranker_top_k_out=4,
    )

    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")

    base = retriever_no_rr.retrieve(q_node.text, expansion, kg)
    ranked = retriever_rr.retrieve(q_node.text, expansion, kg)

    # Reranker truncates to top_k_out
    assert len(ranked) <= 4
    # Ordering is changed (we use a deterministic mock that scores by overlap)
    # — at minimum, ranked must be a permutation/subset of base
    base_ids = {d.node_id for d in base}
    for d in ranked:
        assert d.node_id in base_ids
