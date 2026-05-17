"""ChromaDB-based persistent vector store with three collections.

Collections:
  - graph_chunks    — text of Chunk nodes from the knowledge graph.
  - graph_concepts  — primary term + definition of Concept nodes.
  - md_chunks       — re-chunks of theory_economics.md for broader RAG coverage.

Each item carries a payload (`metadata` in Chroma terminology) with at minimum:
  { "node_id": str, "node_type": str, "node_offset": int|None, "section": str|None }

Cosine similarity is achieved by storing L2-normalized vectors and using
distance: "cosine" (Chroma default). Search returns documents ranked by
similarity (we convert distance -> similarity = 1 - distance).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_CHUNKS = "graph_chunks"
GRAPH_CONCEPTS = "graph_concepts"
MD_CHUNKS = "md_chunks"
ALL_COLLECTIONS = (GRAPH_CHUNKS, GRAPH_CONCEPTS, MD_CHUNKS)


@dataclass
class Hit:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]


def _coerce_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata supports str/int/float/bool only; coerce or drop None."""
    cleaned: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            cleaned[k] = str(v)
    return cleaned


class VectorStore:
    """Thin wrapper over chromadb.PersistentClient."""

    def __init__(self, persist_dir: str | Path) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        persist_dir = Path(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        # Lazy collections: created on demand.
        self._collections: dict[str, Any] = {}

    def _get(self, name: str):
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    def reset(self, name: str | None = None) -> None:
        if name is None:
            for n in ALL_COLLECTIONS:
                try:
                    self._client.delete_collection(n)
                except Exception:
                    pass
            self._collections.clear()
        else:
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
            self._collections.pop(name, None)

    def count(self, name: str) -> int:
        return self._get(name).count()

    def is_ready(self) -> bool:
        return all(self.count(n) > 0 for n in ALL_COLLECTIONS)

    def add_batch(
        self,
        name: str,
        ids: list[str],
        embeddings: np.ndarray,
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if len(ids) == 0:
            return
        col = self._get(name)
        col.add(
            ids=ids,
            embeddings=[v.tolist() for v in embeddings],
            documents=documents,
            metadatas=[_coerce_metadata(m) for m in metadatas],
        )

    def search(
        self,
        name: str,
        query_embedding: np.ndarray,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[Hit]:
        col = self._get(name)
        if col.count() == 0:
            return []
        res = col.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(top_k, col.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[Hit] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, _id in enumerate(ids):
            distance = float(dists[i]) if i < len(dists) else 1.0
            score = 1.0 - distance  # cosine similarity
            hits.append(
                Hit(
                    id=str(_id),
                    score=score,
                    text=str(docs[i]) if i < len(docs) else "",
                    metadata=dict(metas[i] or {}) if i < len(metas) else {},
                )
            )
        return hits

    def search_many(
        self,
        searches: Iterable[tuple[str, np.ndarray, int]],
    ) -> dict[str, list[Hit]]:
        return {name: self.search(name, q, k) for name, q, k in searches}
