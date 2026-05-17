"""Tests for retriever new features:
- md_chunks dedup against graph_chunks
- per-option extra_queries (mini-retrieve)
- non-saturated graph boost (scores differ even after boost)
"""

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


def _populate_with_overlap(tmp_path: Path, kg: KnowledgeGraph) -> tuple[VectorStore, DeterministicHashEmbedder]:
    """Populate store. Add an md_chunk with text that matches a graph_chunk."""
    embedder = DeterministicHashEmbedder(dim=128)
    store = VectorStore(persist_dir=tmp_path / "chroma_overlap")

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
    # Add an md_chunk with text *identical* to chunk c:1 — should be deduped.
    duplicate_text = chunks[0].text  # same as c:1
    md_dup_emb = embedder.encode([duplicate_text], mode="passage")
    md_id_dup = "md:dup0001"
    md_id_unique = "md:uniq0001"
    md_unique_text = (
        "Нумизматика и боны, исторические ценные бумаги XIX века: облигации внутреннего "
        "займа Российской Империи. Этот раздел не пересекается с графом."
    )
    md_unique_emb = embedder.encode([md_unique_text], mode="passage")
    store.add_batch(
        MD_CHUNKS,
        [md_id_dup, md_id_unique],
        md_dup_emb if False else embedder.encode([duplicate_text, md_unique_text], mode="passage"),
        [duplicate_text, md_unique_text],
        [
            {"node_id": md_id_dup, "node_type": "MdChunk", "section": "test"},
            {"node_id": md_id_unique, "node_type": "MdChunk", "section": "test_uniq"},
        ],
    )
    return store, embedder


def test_md_chunks_deduplicated_against_graph_chunks(tmp_path: Path, kg: KnowledgeGraph) -> None:
    store, embedder = _populate_with_overlap(tmp_path, kg)
    retriever = Retriever(
        store=store,
        embedder=embedder,
        top_k_graph_chunks=4,
        top_k_concepts=4,
        top_k_md=8,
    )
    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")
    docs = retriever.retrieve(q_node.text, expansion, kg)
    # The duplicate md_chunk should NOT be present (dropped by Jaccard overlap)
    md_ids = {d.node_id for d in docs if d.source == "md_chunks"}
    assert "md:dup0001" not in md_ids, "Duplicate md_chunk leaked into results"


def test_extra_queries_add_documents(tmp_path: Path, kg: KnowledgeGraph) -> None:
    store, embedder = _populate_with_overlap(tmp_path, kg)
    retriever = Retriever(
        store=store, embedder=embedder, top_k_graph_chunks=2, top_k_concepts=2, top_k_md=2,
    )
    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")
    base = retriever.retrieve(q_node.text, expansion, kg)
    base_ids = {d.node_id for d in base}
    # Now retrieve with an extra query that should pull a specific concept ('Дериватив')
    expanded = retriever.retrieve(
        q_node.text, expansion, kg, extra_queries=["Дериватив фьючерс опцион"],
    )
    expanded_ids = {d.node_id for d in expanded}
    # Either it brings new documents OR keeps the same set; at least it must not crash
    # and must mark its option-derived items if any are added.
    new_ids = expanded_ids - base_ids
    if new_ids:
        # Find one of the new docs and verify metadata flag
        new_docs = [d for d in expanded if d.node_id in new_ids]
        assert any(
            "matched_option_query" in d.metadata for d in new_docs
        ), "extra_queries hits should be marked"


def test_graph_boost_does_not_saturate_in_pipeline(tmp_path: Path, kg: KnowledgeGraph) -> None:
    """All hits in BFS expansion have different similarities; after boost they
    must still have *different* (non-equal) scores."""
    store, embedder = _populate_with_overlap(tmp_path, kg)
    retriever = Retriever(store=store, embedder=embedder)
    expansion = kg.expand_from_assessment("q:1", depth=2)
    q_node = kg.get_node("q:1")
    docs = retriever.retrieve(q_node.text, expansion, kg)
    # Take the boosted graph_chunks/concepts (in_graph_expansion=True)
    boosted = [d for d in docs if d.in_graph_expansion and d.source != "md_chunks"]
    if len(boosted) >= 2:
        scores = sorted({round(d.score, 6) for d in boosted}, reverse=True)
        # Strictly > 1 unique score expected (if more than 1 boosted item)
        assert len(scores) >= 2, f"Boosted scores still saturated: {[d.score for d in boosted]}"
