"""Tests for the low-content node filter applied to related_concepts and retriever boost."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.schemas import AnalyzeTestRequest, TestResultItem
from app.graph.knowledge_graph import KnowledgeGraph
from app.graph.loader import load_concept_dictionary, load_graph
from app.graph.topics import cluster_concepts
from app.rag.embeddings import DeterministicHashEmbedder
from app.rag.generator import Generator
from app.rag.retriever import MIN_USEFUL_CONTENT_CHARS, Retriever
from app.rag.vectorstore import GRAPH_CHUNKS, GRAPH_CONCEPTS, VectorStore
from app.services.analyze import _has_useful_content, analyze_test


@pytest.fixture
def kg_with_skeleton(tmp_path: Path) -> KnowledgeGraph:
    """Graph with one rich concept, one skeleton (empty definition) concept,
    and an Assessment that links to both."""
    graph = {
        "_meta": {"test": True},
        "nodes": [
            {"id": "q:1", "type": "Assessment", "text": "Что такое реестр?", "difficulty": 2},
            {
                "id": "c:1",
                "type": "Chunk",
                "text": "Реестр — список владельцев именных ценных бумаг на дату.",
                "definition": "Учет владельцев",
            },
            {
                "id": "p:rich",
                "type": "Concept",
                "text": "Реестр владельцев",
                "definition": (
                    "Список владельцев именных ценных бумаг, составленный на определенную дату; "
                    "ведется регистратором по договору с эмитентом."
                ),
            },
            {
                "id": "p:skeleton",
                "type": "Concept",
                "text": "Х",  # very short, no definition
                "definition": "",
            },
        ],
        "edges": [
            {"source": "q:1", "target": "c:1", "type": "TESTS", "weight": 0.9},
            {"source": "c:1", "target": "p:rich", "type": "ELABORATES", "weight": 0.8},
            {"source": "c:1", "target": "p:skeleton", "type": "MENTIONS", "weight": 0.5},
        ],
    }
    concepts = {
        "_meta": {"test": True},
        "concepts": [
            {
                "concept_id": "p:rich",
                "term": {"primary": "Реестр владельцев", "aliases": []},
                "definition": "Список владельцев именных ценных бумаг.",
            },
            {
                "concept_id": "p:skeleton",
                "term": {"primary": "Х", "aliases": []},
                "definition": "",
            },
        ],
    }
    gp = tmp_path / "g.json"
    cp = tmp_path / "c.json"
    gp.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    cp.write_text(json.dumps(concepts, ensure_ascii=False), encoding="utf-8")
    return KnowledgeGraph(load_graph(gp), load_concept_dictionary(cp))


def test_has_useful_content_truthtable(kg_with_skeleton: KnowledgeGraph) -> None:
    expansion = kg_with_skeleton.expand_from_assessment("q:1", depth=2)
    items_by_id = {it.node.id: it for it in expansion.items}
    assert "p:rich" in items_by_id
    assert "p:skeleton" in items_by_id
    assert _has_useful_content(items_by_id["p:rich"]) is True
    assert _has_useful_content(items_by_id["p:skeleton"]) is False


def test_min_useful_content_constant_is_reasonable() -> None:
    # Guardrail: don't accidentally make the threshold so high it filters real concepts.
    assert 50 <= MIN_USEFUL_CONTENT_CHARS <= 200


def test_skeleton_concept_excluded_from_related_concepts(
    kg_with_skeleton: KnowledgeGraph,
    tmp_path: Path,
) -> None:
    embedder = DeterministicHashEmbedder(dim=64)
    store = VectorStore(persist_dir=tmp_path / "chroma_skel")
    chunks = kg_with_skeleton.chunks()
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
    concepts = kg_with_skeleton.concepts()
    concept_texts = [n.text + ". " + n.definition for n in concepts]
    concept_embs = embedder.encode(concept_texts, mode="passage")
    store.add_batch(
        GRAPH_CONCEPTS,
        [n.id for n in concepts],
        concept_embs,
        concept_texts,
        [{"node_id": n.id, "node_type": "Concept"} for n in concepts],
    )

    retriever = Retriever(store=store, embedder=embedder)
    generator = Generator.__new__(Generator)
    generator._model = "fake"  # type: ignore[attr-defined]
    generator._max_tokens = 100  # type: ignore[attr-defined]
    generator._client = None  # type: ignore[attr-defined]

    import os
    os.environ["SKIP_LLM"] = "1"
    from app.core.config import get_settings
    get_settings.cache_clear()

    topics_bundle = cluster_concepts(
        kg_with_skeleton,
        [c.id for c in concepts],
        concept_embs,
        n_clusters=2,
    )

    req = AnalyzeTestRequest(
        user_id=1,
        test_results=[TestResultItem(question_id="q:1", is_correct=False)],
    )
    resp = analyze_test(req, kg_with_skeleton, retriever, generator, topics_bundle)
    item = resp.study_plan[0]  # type: ignore[union-attr]
    assert "p:skeleton" not in item.related_concepts
    assert "p:rich" in item.related_concepts
    # Sources also should not contain the skeleton (because it falls below the threshold
    # in the retriever's graph-grounding injection).
    assert all(s.node_id != "p:skeleton" for s in item.sources)
