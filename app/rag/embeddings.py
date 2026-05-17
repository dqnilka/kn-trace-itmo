"""Embeddings wrapper around sentence-transformers.

Uses `intfloat/multilingual-e5-small` by default (excellent quality on Russian
retrieval, ~470MB). E5 expects "query: ..." / "passage: ..." prefixes which we
inject automatically.

For unit tests we provide `DeterministicHashEmbedder` — produces stable vectors
without downloading any model.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Iterable, Literal

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

EmbeddingMode = Literal["query", "passage"]


class BaseEmbedder(ABC):
    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def encode(self, texts: list[str], mode: EmbeddingMode = "passage") -> np.ndarray: ...


class E5Embedder(BaseEmbedder):
    """sentence-transformers wrapper with E5 prefixing and L2 normalization."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", device: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name, device=device)
        self._model_name = model_name
        # Probe dim
        probe = self._model.encode(["passage: probe"], normalize_embeddings=True)
        self._dim = int(probe.shape[1])
        logger.info("Embedding model loaded. dim=%d", self._dim)

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str], mode: EmbeddingMode = "passage") -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        prefix = "query: " if mode == "query" else "passage: "
        prepared = [prefix + (t or "") for t in texts]
        vecs = self._model.encode(
            prepared,
            normalize_embeddings=True,
            batch_size=32,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32, copy=False)


class DeterministicHashEmbedder(BaseEmbedder):
    """Deterministic, dependency-free embedder for tests.

    Produces stable, low-dim normalized vectors based on token hashing
    (a tiny bag-of-features). Not a real semantic encoder, but good enough
    to verify retrieval ordering in unit tests.
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self._dim, dtype=np.float32)
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if (h & 1) else -1.0
            v[idx] += sign
        n = np.linalg.norm(v)
        if n > 0:
            v /= n
        return v

    def encode(self, texts: list[str], mode: EmbeddingMode = "passage") -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return np.vstack([self._vec(t or "") for t in texts])


def cosine_topk(query_vec: np.ndarray, matrix: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (indices, scores) for top-k similar rows in `matrix` (assumed L2-normalized)."""
    if matrix.size == 0:
        return np.empty(0, dtype=int), np.empty(0, dtype=np.float32)
    sims = matrix @ query_vec
    k = min(k, matrix.shape[0])
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return idx, sims[idx]


def batched(iterable: Iterable, n: int):
    batch: list = []
    for it in iterable:
        batch.append(it)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch
