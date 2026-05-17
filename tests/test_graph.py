"""Unit tests for KnowledgeGraph BFS expansion and topic helpers."""

from __future__ import annotations

import pytest

from app.graph.knowledge_graph import KnowledgeGraph


def test_loader_basic(kg: KnowledgeGraph) -> None:
    assert kg.total_nodes == 8
    assert kg.total_edges == 8
    assert kg.has_node("q:1")
    assert {n.type for n in kg.assessments()} == {"Assessment"}
    assert len(kg.concepts()) == 3
    assert len(kg.chunks()) == 2


def test_expand_q1_depth_2_includes_chunk_and_concepts(kg: KnowledgeGraph) -> None:
    res = kg.expand_from_assessment("q:1", depth=2)
    found_ids = {it.node.id for it in res.items}
    # L1: c:1 (via TESTS)
    assert "c:1" in found_ids
    # L2: p:obligation (via c:1 -> ELABORATES) and p:security (via c:1 -> MENTIONS)
    assert "p:obligation" in found_ids
    assert "p:security" in found_ids
    # Should NOT include the seed node itself
    assert "q:1" not in found_ids
    # No unrelated concept
    assert "p:derivative" not in found_ids


def test_expansion_scores_are_descending(kg: KnowledgeGraph) -> None:
    res = kg.expand_from_assessment("q:1", depth=2)
    scores = [it.score for it in res.items]
    assert scores == sorted(scores, reverse=True)
    # Top item should be c:1 (direct TESTS hit)
    assert res.items[0].node.id == "c:1"


def test_q2_directly_tests_concept(kg: KnowledgeGraph) -> None:
    res = kg.expand_from_assessment("q:2", depth=2)
    found_ids = {it.node.id for it in res.items}
    # L1: p:security via TESTS
    assert "p:security" in found_ids
    # L2 from p:security via PREREQUISITE -> p:obligation (out direction)
    assert "p:obligation" in found_ids


def test_unknown_assessment_raises(kg: KnowledgeGraph) -> None:
    with pytest.raises(KeyError):
        kg.expand_from_assessment("q:no-such", depth=2)


def test_depth_validation(kg: KnowledgeGraph) -> None:
    with pytest.raises(ValueError):
        kg.expand_from_assessment("q:1", depth=0)


def test_assessments_related_to_concepts(kg: KnowledgeGraph) -> None:
    # Concept p:security is directly TESTed by q:2 and indirectly mentioned by c:1 (q:1 chunk)
    res = kg.assessments_related_to_concepts(["p:security"], top_k=5)
    ids = [n.id for n, _ in res]
    assert "q:2" in ids
    # q:1 should also surface (indirectly via c:1 which MENTIONS p:security and is TESTed by q:1)
    assert "q:1" in ids
    # q:3 (about derivatives) should NOT be in the result
    assert "q:3" not in ids


def test_find_concept_by_term(kg: KnowledgeGraph) -> None:
    assert kg.find_concept_by_term("Облигация") == "p:obligation"
    assert kg.find_concept_by_term("облига") == "p:obligation"  # alias
    assert kg.find_concept_by_term(" ЦБ ") == "p:security"  # whitespace + casing
    assert kg.find_concept_by_term("неизвестно") is None


def test_concept_centrality(kg: KnowledgeGraph) -> None:
    centrality = kg.concept_centrality()
    # p:obligation: in: ELABORATES from c:1, PREREQUISITE from p:security  -> 2 in
    # p:obligation: out: 0
    assert centrality["p:obligation"] == 2
    assert "p:security" in centrality and centrality["p:security"] >= 2
