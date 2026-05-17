"""Shared fixtures: small synthetic graph and concept dictionary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.graph.knowledge_graph import KnowledgeGraph
from app.graph.loader import (
    LoadedConceptDictionary,
    LoadedGraph,
    load_concept_dictionary,
    load_graph,
)


# ----------------------------------------------------------------
# Synthetic graph fixture
# ----------------------------------------------------------------
#
# Topology (edge directions follow the real k2-18 conventions):
#
#       Q1 (Assessment, difficulty=3)
#         |
#         | TESTS (Q1 -> Chunk c1)
#         v
#       c1 (Chunk: "Облигации: купонный доход")
#         |
#         | ELABORATES (c1 -> p_obligation)
#         v
#       p_obligation (Concept: "Облигация")
#         ^
#         | PREREQUISITE (p_security -> p_obligation)
#         |
#       p_security (Concept: "Ценная бумага")
#
#       c1 -- MENTIONS --> p_security
#
#       Q2 (Assessment, difficulty=2) -- TESTS --> p_security
#       Q3 (Assessment, difficulty=4) -- TESTS --> c2
#       c2 (Chunk: "Производные финансовые инструменты")
#       c2 -- ELABORATES --> p_derivative (Concept: "Дериватив")
#
# We expect:
#   expand_from_assessment(Q1, depth=2) returns:
#     L1: c1 (TESTS direct)
#     L2: p_obligation (via ELABORATES from c1), p_security (via MENTIONS from c1)
#     and PREREQUISITE p_security <- p_obligation should reach p_obligation→p_security
#     too (already covered).


@pytest.fixture
def synthetic_graph_dict() -> dict:
    return {
        "_meta": {"test": True},
        "nodes": [
            {
                "id": "q:1",
                "type": "Assessment",
                "text": "Что такое купонный доход облигации?",
                "difficulty": 3,
                "node_offset": 100,
            },
            {
                "id": "q:2",
                "type": "Assessment",
                "text": "Дайте определение ценной бумаги.",
                "difficulty": 2,
                "node_offset": 200,
            },
            {
                "id": "q:3",
                "type": "Assessment",
                "text": "Назовите пример производного инструмента.",
                "difficulty": 4,
                "node_offset": 800,
            },
            {
                "id": "c:1",
                "type": "Chunk",
                "text": (
                    "Облигации: купонный доход определяется как процент от номинала ценной "
                    "бумаги; периодичность выплат и ставка устанавливаются эмитентом при выпуске."
                ),
                "definition": "Купонный доход облигации",
                "difficulty": 2,
                "node_offset": 110,
            },
            {
                "id": "c:2",
                "type": "Chunk",
                "text": (
                    "Производные финансовые инструменты: фьючерсы, форварды, опционы и свопы. "
                    "Их стоимость зависит от цены базового актива."
                ),
                "definition": "Деривативы и срочные контракты",
                "difficulty": 3,
                "node_offset": 810,
            },
            {
                "id": "p:obligation",
                "type": "Concept",
                "text": "Облигация",
                "definition": (
                    "Долговая эмиссионная ценная бумага, закрепляющая право её владельца на "
                    "получение номинальной стоимости и зафиксированного процента от неё."
                ),
                "node_offset": 120,
            },
            {
                "id": "p:security",
                "type": "Concept",
                "text": "Ценная бумага",
                "definition": (
                    "Документ установленной формы, удостоверяющий с соблюдением закона имущественные "
                    "права, осуществление или передача которых возможны только при его предъявлении."
                ),
                "node_offset": 50,
            },
            {
                "id": "p:derivative",
                "type": "Concept",
                "text": "Дериватив",
                "definition": (
                    "Производный финансовый инструмент: контракт, стоимость которого зависит от "
                    "цены одного или нескольких базовых активов (акции, облигации, индексы, валюта)."
                ),
                "node_offset": 820,
            },
        ],
        "edges": [
            {"source": "q:1", "target": "c:1", "type": "TESTS", "weight": 0.9},
            {"source": "c:1", "target": "p:obligation", "type": "ELABORATES", "weight": 0.8},
            {"source": "c:1", "target": "p:security", "type": "MENTIONS", "weight": 0.5},
            {"source": "p:security", "target": "p:obligation", "type": "PREREQUISITE", "weight": 0.7},
            # Q2 directly TESTS a concept
            {"source": "q:2", "target": "p:security", "type": "TESTS", "weight": 0.9},
            # Q3 -> c2 -> p:derivative
            {"source": "q:3", "target": "c:2", "type": "TESTS", "weight": 0.9},
            {"source": "c:2", "target": "p:derivative", "type": "ELABORATES", "weight": 0.8},
            # Reverse-direction TESTS (rare but exists in real data) — chunk testing assessment
            {"source": "c:2", "target": "q:3", "type": "PARALLEL", "weight": 0.4},
        ],
    }


@pytest.fixture
def synthetic_concepts_dict() -> dict:
    return {
        "_meta": {"test": True},
        "concepts": [
            {
                "concept_id": "p:obligation",
                "term": {"primary": "Облигация", "aliases": ["bond", "облига"]},
                "definition": "Долговая ценная бумага.",
            },
            {
                "concept_id": "p:security",
                "term": {"primary": "Ценная бумага", "aliases": ["security", "ЦБ"]},
                "definition": "Документ, удостоверяющий имущественные права.",
            },
            {
                "concept_id": "p:derivative",
                "term": {"primary": "Дериватив", "aliases": ["производный инструмент"]},
                "definition": "Производный финансовый инструмент.",
            },
        ],
    }


@pytest.fixture
def synthetic_graph_path(tmp_path: Path, synthetic_graph_dict: dict) -> Path:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(synthetic_graph_dict, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def synthetic_concepts_path(tmp_path: Path, synthetic_concepts_dict: dict) -> Path:
    p = tmp_path / "concepts.json"
    p.write_text(json.dumps(synthetic_concepts_dict, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def loaded_graph(synthetic_graph_path: Path) -> LoadedGraph:
    return load_graph(synthetic_graph_path)


@pytest.fixture
def loaded_concepts(synthetic_concepts_path: Path) -> LoadedConceptDictionary:
    return load_concept_dictionary(synthetic_concepts_path)


@pytest.fixture
def kg(loaded_graph: LoadedGraph, loaded_concepts: LoadedConceptDictionary) -> KnowledgeGraph:
    return KnowledgeGraph(loaded_graph, loaded_concepts)
