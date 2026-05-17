"""Standalone CLI: build ``theme_sections.json`` from an existing graph.

The full strict pipeline can also do this via ``--link-theory``, but that path
rebuilds task↔concept links and ALWAYS overwrites ``graph.json`` (LLM rerank
results disappear unless you re-pass the flags). This script reads the
existing graph + bank and produces only ``theme_sections.json`` — safe to run
multiple times.

Run::

    docker compose run --rm api python -m app.pipeline.link_theory \\
        --exam fsfr-basic [--top-n 6] [--min-score 0.35]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.exams.registry import ExamRegistry, UnknownExamError, load_bank
from app.pipeline.link_theory_to_themes import (
    link_theory_to_themes,
    save_theme_sections,
)
from app.rag.embeddings import E5Embedder
from app.rag.vectorstore import VectorStore

logger = get_logger(__name__)


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m app.pipeline.link_theory")
    p.add_argument("--exam", required=True)
    p.add_argument("--top-n", type=int, default=6)
    p.add_argument("--min-score", type=float, default=0.35)
    args = p.parse_args()

    settings = get_settings()
    registry = ExamRegistry(settings.exams_dir)
    try:
        exam = registry.get(args.exam)
    except UnknownExamError:
        logger.error("Unknown exam: %s", args.exam)
        return 2

    graph_path = exam.root / "graph.json"
    if not graph_path.exists():
        logger.error("graph.json missing at %s — run app.pipeline.strict first", graph_path)
        return 3
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    bank = load_bank(exam)

    logger.info("Initializing embedder %s", settings.embedding_model)
    embedder = E5Embedder(model_name=settings.embedding_model)
    store = VectorStore(persist_dir=settings.chroma_path)

    links, meta = link_theory_to_themes(
        graph=graph,
        bank=bank,
        embedder=embedder,
        store=store,
        top_n=args.top_n,
        min_score=args.min_score,
    )
    out = exam.root / "theme_sections.json"
    save_theme_sections(links, out, meta)
    print(json.dumps({"links": len(links), "output": str(out), "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
