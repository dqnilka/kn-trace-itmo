"""Service-layer tests using extractive generator (no LLM call)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.api.schemas import (
    AnalyzeTestErrorsResponse,
    AnalyzeTestPerfectResponse,
    AnalyzeTestRequest,
    TestResultItem,
)
from app.graph.knowledge_graph import KnowledgeGraph
from app.graph.topics import cluster_concepts
from app.rag.embeddings import DeterministicHashEmbedder
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from app.rag.vectorstore import GRAPH_CHUNKS, GRAPH_CONCEPTS, VectorStore
from app.services.analyze import UnknownAssessmentError, analyze_test
from app.services.topic_dive import UnknownTopicError, topic_dive


def _build_stack(tmp_path: Path, kg: KnowledgeGraph):
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

    retriever = Retriever(store=store, embedder=embedder)
    generator = Generator.__new__(Generator)
    generator._model = "fake"  # type: ignore[attr-defined]
    generator._max_tokens = 100  # type: ignore[attr-defined]
    generator._client = None  # type: ignore[attr-defined]

    # Force extractive mode via env
    import os
    os.environ["SKIP_LLM"] = "1"
    from app.core.config import get_settings
    get_settings.cache_clear()

    topics = cluster_concepts(kg, [c.id for c in concepts], concept_embs, n_clusters=2)
    return retriever, generator, topics


def test_analyze_test_with_errors(tmp_path: Path, kg: KnowledgeGraph) -> None:
    retriever, generator, topics = _build_stack(tmp_path, kg)
    req = AnalyzeTestRequest(
        user_id=42,
        test_results=[
            TestResultItem(question_id="q:1", is_correct=False),
            TestResultItem(question_id="q:2", is_correct=True),
            TestResultItem(question_id="q:3", is_correct=False),
        ],
    )
    resp = analyze_test(req, kg, retriever, generator, topics)
    assert isinstance(resp, AnalyzeTestErrorsResponse)
    assert resp.status == "errors_found"
    assert resp.user_id == 42
    assert resp.total_questions == 3
    assert resp.correct_count == 1
    assert resp.incorrect_count == 2
    assert len(resp.study_plan) == 2
    failed_ids = {item.failed_question_id for item in resp.study_plan}
    assert failed_ids == {"q:1", "q:3"}
    for item in resp.study_plan:
        assert item.related_concepts, "related_concepts must be non-empty"
        assert item.theory_content
        assert item.sources


def test_analyze_test_perfect_score(tmp_path: Path, kg: KnowledgeGraph) -> None:
    retriever, generator, topics = _build_stack(tmp_path, kg)
    req = AnalyzeTestRequest(
        user_id=7,
        test_results=[
            TestResultItem(question_id="q:1", is_correct=True),
            TestResultItem(question_id="q:2", is_correct=True),
        ],
    )
    resp = analyze_test(req, kg, retriever, generator, topics)
    assert isinstance(resp, AnalyzeTestPerfectResponse)
    assert resp.status == "perfect_score"
    assert resp.available_topics


def test_analyze_test_unknown_question(tmp_path: Path, kg: KnowledgeGraph) -> None:
    retriever, generator, topics = _build_stack(tmp_path, kg)
    req = AnalyzeTestRequest(
        user_id=1,
        test_results=[TestResultItem(question_id="q:does-not-exist", is_correct=False)],
    )
    with pytest.raises(UnknownAssessmentError):
        analyze_test(req, kg, retriever, generator, topics)


def test_topic_dive_returns_questions(tmp_path: Path, kg: KnowledgeGraph) -> None:
    _, _, topics = _build_stack(tmp_path, kg)
    name = topics.topics[0].name
    resp = topic_dive(name, kg, topics, top_k=5)
    assert resp.topic_name == name
    # In our synthetic graph some topics may have 0 related assessments,
    # but at least one topic must yield questions; iterate to find it.
    if not resp.questions:
        for t in topics.topics:
            r = topic_dive(t.name, kg, topics, top_k=5)
            if r.questions:
                resp = r
                break
    assert resp.questions, "Expected at least one topic with questions"


def test_topic_dive_unknown(tmp_path: Path, kg: KnowledgeGraph) -> None:
    _, _, topics = _build_stack(tmp_path, kg)
    with pytest.raises(UnknownTopicError):
        topic_dive("__nope__", kg, topics)
