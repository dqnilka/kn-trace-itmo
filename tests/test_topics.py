"""Tests for topic clustering."""

from __future__ import annotations

import numpy as np

from app.graph.knowledge_graph import KnowledgeGraph
from app.graph.topics import cluster_concepts, load_topics, save_topics


def _normalize(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)


def test_cluster_concepts_basic(kg: KnowledgeGraph, tmp_path) -> None:
    concept_ids = [c.id for c in kg.concepts()]
    # Synthetic embeddings: two clear clusters.
    rng = np.random.default_rng(0)
    base_a = rng.normal(loc=[1.0, 0.0, 0.0], scale=0.05, size=(len(concept_ids), 3))
    # Place 'p:derivative' far from the others
    embs = base_a.copy()
    idx_deriv = concept_ids.index("p:derivative")
    embs[idx_deriv] = np.array([0.0, 1.0, 0.0]) + rng.normal(scale=0.05, size=3)

    embs = _normalize(embs)

    bundle = cluster_concepts(kg, concept_ids, embs, n_clusters=2, random_state=42)
    assert len(bundle.topics) == 2
    sizes = sorted(t.size for t in bundle.topics)
    assert sizes == [1, 2]

    # The cluster with derivative should have size 1 and name 'Дериватив'
    deriv_topic = next(t for t in bundle.topics if "p:derivative" in t.concept_ids)
    assert deriv_topic.name == "Дериватив"
    assert deriv_topic.centroid_concept_id == "p:derivative"


def test_topics_serialization_roundtrip(kg: KnowledgeGraph, tmp_path) -> None:
    concept_ids = [c.id for c in kg.concepts()]
    embs = _normalize(np.eye(len(concept_ids), 3))
    bundle = cluster_concepts(kg, concept_ids, embs, n_clusters=2)
    p = tmp_path / "topics.json"
    save_topics(bundle, p)
    loaded = load_topics(p)
    assert len(loaded.topics) == len(bundle.topics)
    assert loaded.topics[0].name == bundle.topics[0].name


def test_find_by_name_case_insensitive(kg: KnowledgeGraph) -> None:
    concept_ids = [c.id for c in kg.concepts()]
    embs = _normalize(np.eye(len(concept_ids), 3))
    bundle = cluster_concepts(kg, concept_ids, embs, n_clusters=2)
    name = bundle.topics[0].name
    assert bundle.find_by_name(name.upper()) is not None
    assert bundle.find_by_name("nonexistent_xyz") is None
