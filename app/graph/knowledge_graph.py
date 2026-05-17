"""Legacy KnowledgeGraph stubs — see app/graph/__init__.py for context.

The original implementation (BFS expansion, low-content filtering, etc.) used
k2-18 LearningChunkGraph data. We dropped runtime loading of that artifact;
this stub just keeps imports working in modules that still mention the types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str = ""
    text: str = ""
    definition: str = ""
    node_offset: int | None = None
    difficulty: int | None = None


@dataclass
class ExpansionItem:
    node: GraphNode
    score: float = 0.0
    via_edge_types: tuple[str, ...] = ()


@dataclass
class ExpansionResult:
    items: list[ExpansionItem] = field(default_factory=list)


class KnowledgeGraph:
    """No-op KG. Construct it if absolutely needed, but methods raise."""

    def __init__(self, graph: Any = None, concept_dict: Any = None) -> None:
        self._graph = graph or {"nodes": [], "edges": []}
        self._cd = concept_dict or {"concepts": []}

    @property
    def total_nodes(self) -> int:
        return len(self._graph.get("nodes", []))

    @property
    def total_edges(self) -> int:
        return len(self._graph.get("edges", []))

    def has_node(self, _node_id: str) -> bool:
        return False

    def get_node(self, _node_id: str) -> GraphNode:
        raise KeyError("Legacy KnowledgeGraph stub does not store nodes")

    def expand_from_assessment(self, _node_id: str, depth: int = 2) -> ExpansionResult:
        return ExpansionResult(items=[])
