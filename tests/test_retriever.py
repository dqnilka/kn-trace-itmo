"""End-to-end retriever test on the synthetic graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.graph.knowledge_graph import KnowledgeGraph
from app.rag.embeddings import DeterministicHashEmbedder
from app.rag.retriever import Retriever
from app.rag.vectorstore import (
    GRAPH_CHUNKS,
    GRAPH_CONCEPTS,
    MD_CHUNKS,
    VectorStore,
)


@pytest.fixture
def populated_store(tmp_path: Path, kg: KnowledgeGraph) -> tuple[VectorStore, DeterministicHashEmbedder]:
    embedder = DeterministicHashEmbedder(dim=128)
    store = VectorStore(persist_dir=tmp_path / "chroma")
    # Index Chunks and Concepts
    chunks = kg.chunks()
    chunk_texts = [(n.definition + ". " + n.text) if n.definition else n.text for n in chunks]
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
    # Empty md_chunks (still needed for the API surface)
    return store, embedder


def test_retriever_returns_graph_grounded_docs(populated_store, kg) -> None:
    store, embedder = populated_store
    retriever = Retriever(
        store=store,
        embedder=embedder,
        top_k_graph_chunks=3,
        top_k_concepts=3,
        top_k_md=3,
    )
    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")
    docs = retriever.retrieve(q_node.text, expansion, kg)
    assert docs, "Retriever returned no documents"
    ids = {d.node_id for d in docs}
    # Graph-expansion-discovered nodes should be present
    assert {"c:1"}.issubset(ids)
    # At least one doc has in_graph_expansion=True
    assert any(d.in_graph_expansion for d in docs)
    # All scores valid
    assert all(0 <= d.score <= 1.05 for d in docs)
