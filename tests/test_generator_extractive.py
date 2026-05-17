"""Extractive-mode generator test (no LLM call)."""

from __future__ import annotations

import os
from pathlib import Path

from app.api.schemas import Source
from app.graph.knowledge_graph import KnowledgeGraph
from app.rag.embeddings import DeterministicHashEmbedder
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from app.rag.vectorstore import GRAPH_CHUNKS, GRAPH_CONCEPTS, VectorStore


def _populate(tmp_path: Path, kg: KnowledgeGraph) -> tuple[VectorStore, DeterministicHashEmbedder]:
    embedder = DeterministicHashEmbedder(dim=128)
    store = VectorStore(persist_dir=tmp_path / "chroma")
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
    return store, embedder


def test_extractive_generation(tmp_path, kg: KnowledgeGraph) -> None:
    store, embedder = _populate(tmp_path, kg)
    retriever = Retriever(store=store, embedder=embedder)
    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")
    docs = retriever.retrieve(q_node.text, expansion, kg)

    # Build a Generator without making any LLM call.
    gen = Generator.__new__(Generator)
    gen._model = "fake"  # type: ignore[attr-defined]
    gen._max_tokens = 100  # type: ignore[attr-defined]
    gen._client = None  # type: ignore[attr-defined]

    out = gen.generate(q_node, expansion, docs, mode="extractive")
    assert out.mode == "extractive"
    assert "Что проверял вопрос" in out.text
    assert any(s.node_id == "c:1" for s in out.sources) or any(
        s.node_id.startswith("p:") for s in out.sources
    )
    assert len(out.text) > 100
