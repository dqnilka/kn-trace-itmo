"""Application-wide singletons / FastAPI dependencies.

Loaded once at startup (``AppContext.startup``) and injected via
``Depends(...)`` into route handlers.

After the strict pipeline switch, we no longer load the legacy k2-18
KnowledgeGraph at startup — chapters/themes/tasks come from the exam bank
and concepts from the per-exam strict graph. Chroma collections built from
the textbook remain (md_chunks + graph_chunks) and are reused by the
bank-explain RAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import Request

from app.admin.runs import RunManager
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.exams.graph_service import GraphRegistry
from app.exams.registry import ExamRegistry
from app.rag.embeddings import BaseEmbedder, E5Embedder
from app.rag.generator import Generator
from app.rag.reranker import BaseReranker, CrossEncoderReranker
from app.rag.retriever import Retriever
from app.rag.vectorstore import ALL_COLLECTIONS, VectorStore

logger = get_logger(__name__)


@dataclass
class AppContext:
    settings: Settings
    store: VectorStore
    embedder: BaseEmbedder
    retriever: Retriever
    generator: Generator
    exams: ExamRegistry
    graphs: GraphRegistry
    runs: RunManager
    ready: bool = True

    @classmethod
    def startup(cls, settings: Optional[Settings] = None) -> "AppContext":
        settings = settings or get_settings()
        if not settings.soy_token:
            raise RuntimeError(
                "SOY_TOKEN is not set. The service requires a Yandex SOY token "
                "for LLM generation. Export SOY_TOKEN before starting."
            )

        chroma_path = Path(settings.chroma_path)
        store = VectorStore(persist_dir=chroma_path)
        for c in ALL_COLLECTIONS:
            cnt = store.count(c)
            logger.info("Collection %s: %d items", c, cnt)
            if cnt == 0:
                raise RuntimeError(
                    f"Vector collection '{c}' is empty. Run ingest first."
                )

        logger.info("Loading embedding model: %s", settings.embedding_model)
        embedder: BaseEmbedder = E5Embedder(model_name=settings.embedding_model)

        reranker: BaseReranker | None = None
        if settings.enable_reranker:
            logger.info("Loading reranker: %s", settings.reranker_model)
            reranker = CrossEncoderReranker(
                model_name=settings.reranker_model,
                score_blend=settings.reranker_score_blend,
            )
        else:
            logger.info("Reranker disabled (ENABLE_RERANKER=false)")

        if reranker is not None:
            top_k_g = max(settings.retriever_top_k_graph, settings.reranker_top_k_in // 4)
            top_k_m = max(settings.retriever_top_k_md, settings.reranker_top_k_in // 4)
        else:
            top_k_g = settings.retriever_top_k_graph
            top_k_m = settings.retriever_top_k_md

        retriever = Retriever(
            store=store,
            embedder=embedder,
            top_k_graph_chunks=top_k_g,
            top_k_concepts=max(2, top_k_g - 1),
            top_k_md=top_k_m,
            reranker=reranker,
            reranker_top_k_out=settings.reranker_top_k_out,
        )

        logger.info("Initializing LLM client...")
        generator = Generator.from_settings()

        logger.info("Loading exam registry from %s", settings.exams_dir)
        exams = ExamRegistry(settings.exams_dir)
        published = exams.published()
        logger.info(
            "Exam registry: %d total, %d published",
            len(list(exams.all())), len(published),
        )
        for e in published:
            logger.info("  - %s (%s)", e.slug, e.title)

        graphs = GraphRegistry()
        for e in exams.published():
            try:
                graphs.get(e)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to preload strict graph for %s: %s", e.slug, exc)

        runs = RunManager()

        return cls(
            settings=settings,
            store=store,
            embedder=embedder,
            retriever=retriever,
            generator=generator,
            exams=exams,
            graphs=graphs,
            runs=runs,
        )


# ----- FastAPI dependency helpers -----


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext | None = getattr(request.app.state, "ctx", None)
    if ctx is None:
        raise RuntimeError("AppContext is not initialized")
    return ctx


def get_retriever(request: Request) -> Retriever:
    return get_ctx(request).retriever


def get_generator(request: Request) -> Generator:
    return get_ctx(request).generator


def get_exams(request: Request) -> ExamRegistry:
    return get_ctx(request).exams


def get_graphs(request: Request) -> GraphRegistry:
    return get_ctx(request).graphs
