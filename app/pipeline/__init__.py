"""Offline pipeline scripts for building exam-specific artifacts.

The strict-mode pipeline takes a pre-structured exam (bank.json with
chapters/themes/tasks already curated) and produces a unified knowledge graph
plus task↔concept links by embedding similarity. LLM is optional and used
only for re-ranking the top candidates.

Run via the API container so all heavy deps (torch, sentence-transformers)
are already installed::

    docker compose run --rm api python -m app.pipeline.strict \\
        --exam fsfr-basic [--limit 100] [--top-k 3] [--llm-rerank]
"""
