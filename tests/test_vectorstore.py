"""Tests for VectorStore + DeterministicHashEmbedder integration."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.rag.embeddings import DeterministicHashEmbedder, cosine_topk
from app.rag.vectorstore import GRAPH_CHUNKS, VectorStore


def test_add_and_search(tmp_path: Path) -> None:
    embedder = DeterministicHashEmbedder(dim=64)
    store = VectorStore(persist_dir=tmp_path / "chroma")

    docs = [
        "Облигация — долговая ценная бумага.",
        "Акция представляет долю в капитале.",
        "Дериватив это производный финансовый инструмент.",
    ]
    ids = ["doc:1", "doc:2", "doc:3"]
    metas = [{"node_id": i, "node_type": "Chunk", "node_offset": 0} for i in ids]
    embs = embedder.encode(docs, mode="passage")

    store.add_batch(GRAPH_CHUNKS, ids, embs, docs, metas)
    assert store.count(GRAPH_CHUNKS) == 3

    q = embedder.encode(["Что такое облигация?"], mode="query")[0]
    hits = store.search(GRAPH_CHUNKS, q, top_k=2)
    assert len(hits) == 2
    # The order is dependent on hashing, but every result must be one of our docs
    returned_ids = {h.id for h in hits}
    assert returned_ids.issubset(set(ids))


def test_cosine_topk_matches_normalized_search() -> None:
    rng = np.random.default_rng(0)
    mat = rng.normal(size=(5, 8)).astype(np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    q = mat[2].copy()  # closest to itself
    idx, scores = cosine_topk(q, mat, k=3)
    assert idx[0] == 2
    assert scores[0] > 0.99
    assert len(idx) == 3
