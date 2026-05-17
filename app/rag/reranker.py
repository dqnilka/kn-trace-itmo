"""Cross-encoder reranker over hybrid retrieval results.

Bi-encoder retrieval (Chroma + sentence-transformers) gives us top-N candidates
quickly. A cross-encoder model — which re-encodes the (query, document) pair
jointly — produces much sharper relevance scores at the cost of O(N) forward
passes. We use it only on top-N (e.g. N=20) and keep the top-K (e.g. K=8)
as the final context for the LLM.

Default model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
  * Multilingual (incl. Russian), trained on MS MARCO via mMARCO.
  * ~120 MB, ~10ms per pair on CPU.

For unit tests we provide `IdentityReranker` (no-op) and `MockReranker`
(deterministic ranking) — no model download required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.logging import get_logger
from app.rag.retriever import RetrievedDoc

logger = get_logger(__name__)


class BaseReranker(ABC):
    """Reranker interface: takes (query, list[RetrievedDoc]) → re-ordered list."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int | None = None,
    ) -> list[RetrievedDoc]: ...


class IdentityReranker(BaseReranker):
    """No-op reranker — returns docs unchanged (truncates to top_k if given)."""

    def rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int | None = None,
    ) -> list[RetrievedDoc]:
        if top_k is not None:
            return docs[:top_k]
        return docs


class CrossEncoderReranker(BaseReranker):
    """Wraps a sentence-transformers CrossEncoder for relevance scoring."""

    def __init__(
        self,
        model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        device: str | None = None,
        max_pairs_per_call: int = 64,
        score_blend: float = 0.7,
    ) -> None:
        """
        Args:
            model_name: HF model id of a CrossEncoder.
            device: 'cpu' / 'cuda' / None (auto).
            max_pairs_per_call: batch size for predict().
            score_blend: how much weight to give CE score vs original retrieval
                score. 1.0 = pure CE; 0.0 = pure retrieval. Default 0.7.
                Both scores are min-max normalized to [0,1] within the batch
                before blending.
        """
        from sentence_transformers import CrossEncoder

        logger.info("Loading cross-encoder reranker: %s", model_name)
        self._model = CrossEncoder(model_name, device=device)
        self._model_name = model_name
        self._batch = max_pairs_per_call
        self._blend = max(0.0, min(1.0, score_blend))
        logger.info("Cross-encoder loaded (blend=%.2f)", self._blend)

    @staticmethod
    def _minmax_norm(values: list[float]) -> list[float]:
        """Map a list of scores to [0, 1] via min-max; constant lists → all 0.5."""
        if not values:
            return []
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return [0.5] * len(values)
        return [(v - lo) / (hi - lo) for v in values]

    def rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int | None = None,
    ) -> list[RetrievedDoc]:
        if not docs or not query:
            return docs[:top_k] if top_k else docs

        pairs = [(query, d.text) for d in docs]
        # CrossEncoder.predict handles batching internally, but we pass batch_size
        # to keep latency predictable.
        ce_scores_raw = self._model.predict(
            pairs,
            batch_size=self._batch,
            show_progress_bar=False,
        )
        ce_scores = [float(s) for s in ce_scores_raw]
        retrieval_scores = [d.score for d in docs]

        ce_norm = self._minmax_norm(ce_scores)
        ret_norm = self._minmax_norm(retrieval_scores)
        blended = [
            self._blend * c + (1.0 - self._blend) * r
            for c, r in zip(ce_norm, ret_norm)
        ]

        # Update each doc with the new combined score; preserve raw CE in metadata
        # for transparency.
        new_docs: list[RetrievedDoc] = []
        for d, new_score, ce_raw in zip(docs, blended, ce_scores):
            md = dict(d.metadata)
            md["ce_score"] = round(ce_raw, 4)
            md["score_before_rerank"] = round(d.score, 4)
            new_docs.append(
                RetrievedDoc(
                    node_id=d.node_id,
                    node_type=d.node_type,
                    text=d.text,
                    score=float(new_score),
                    source=d.source,
                    metadata=md,
                    in_graph_expansion=d.in_graph_expansion,
                    via_edge_types=d.via_edge_types,
                )
            )
        new_docs.sort(key=lambda x: x.score, reverse=True)
        if top_k is not None:
            new_docs = new_docs[:top_k]
        return new_docs


class MockReranker(BaseReranker):
    """Deterministic reranker for unit tests.

    Scores docs by counting how many query tokens (length>=3) appear in the doc text.
    """

    def __init__(self) -> None:
        pass

    def rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int | None = None,
    ) -> list[RetrievedDoc]:
        import re

        q_tokens = {
            t.lower()
            for t in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", query or "")
        }
        scored: list[tuple[float, RetrievedDoc]] = []
        for d in docs:
            d_tokens = {
                t.lower()
                for t in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", d.text or "")
            }
            overlap = len(q_tokens & d_tokens)
            new_score = float(overlap) + d.score * 0.01  # tiny tiebreak
            scored.append((new_score, d))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        ranked = [d for _, d in scored]
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked
