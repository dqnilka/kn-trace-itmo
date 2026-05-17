"""Ingestion pipeline:
  1. Load LearningChunkGraph + ConceptDictionary.
  2. Embed Chunk nodes  -> graph_chunks collection.
  3. Embed Concept nodes (term + definition) -> graph_concepts collection.
  4. Re-chunk theory_economics.md, embed -> md_chunks collection.
  5. Cluster concept embeddings into topics; save to data/topics.json.
  6. Write a stamp file (manifest hash) so subsequent runs are idempotent.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.graph.knowledge_graph import KnowledgeGraph
from app.graph.loader import load_concept_dictionary, load_graph
from app.graph.topics import cluster_concepts, save_topics
from app.rag.embeddings import BaseEmbedder, E5Embedder
from app.rag.md_chunker import chunk_markdown
from app.rag.vectorstore import (
    ALL_COLLECTIONS,
    GRAPH_CHUNKS,
    GRAPH_CONCEPTS,
    MD_CHUNKS,
    VectorStore,
)

logger = get_logger(__name__)


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            h.update(p.name.encode())
            h.update(str(p.stat().st_size).encode())
            h.update(str(int(p.stat().st_mtime)).encode())
    return h.hexdigest()


def _stamp_path(data_dir: Path) -> Path:
    return data_dir / "ingest.stamp.json"


def _read_stamp(data_dir: Path) -> dict[str, Any]:
    p = _stamp_path(data_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_stamp(data_dir: Path, payload: dict[str, Any]) -> None:
    p = _stamp_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ingest(force: bool = False, embedder: BaseEmbedder | None = None) -> dict[str, Any]:
    """Run full ingestion. Returns a summary dict."""
    settings = get_settings()
    configure_logging(settings.log_level)

    graph_path = Path(settings.graph_path)
    concept_path = Path(settings.concept_dict_path)
    md_path = Path(settings.theory_md_path)
    data_dir = Path(settings.data_dir)
    chroma_path = Path(settings.chroma_path)
    topics_path = Path(settings.topics_path)

    files_hash = _hash_files([graph_path, concept_path, md_path])
    manifest_key = {
        "embedding_model": settings.embedding_model,
        "files_hash": files_hash,
        "n_topics": settings.n_topics,
        "md_target_tokens": settings.md_chunk_target_tokens,
        "md_overlap_tokens": settings.md_chunk_overlap_tokens,
    }

    stamp = _read_stamp(data_dir)
    store = VectorStore(persist_dir=chroma_path)
    if (
        not force
        and stamp.get("manifest") == manifest_key
        and all(store.count(c) > 0 for c in ALL_COLLECTIONS)
        and topics_path.exists()
    ):
        logger.info("Ingest is up to date (stamp matches). Skipping.")
        return {
            "status": "skipped",
            "graph_chunks": store.count(GRAPH_CHUNKS),
            "graph_concepts": store.count(GRAPH_CONCEPTS),
            "md_chunks": store.count(MD_CHUNKS),
        }

    if force:
        logger.info("Force-refresh requested: resetting all collections.")
        store.reset()

    # Load artifacts
    logger.info("Loading graph from %s", graph_path)
    g = load_graph(graph_path)
    logger.info("Loading concept dictionary from %s", concept_path)
    cd = load_concept_dictionary(concept_path)
    kg = KnowledgeGraph(g, cd)
    logger.info("Graph: %d nodes, %d edges", kg.total_nodes, kg.total_edges)

    # Embedder
    if embedder is None:
        embedder = E5Embedder(model_name=settings.embedding_model)

    # 1. graph_chunks
    chunks = kg.chunks()
    logger.info("Embedding %d graph chunks", len(chunks))
    chunk_texts = [
        (n.definition + ". " + n.text).strip() if n.definition else n.text
        for n in chunks
    ]
    chunk_embs = embedder.encode(chunk_texts, mode="passage")
    chunk_metas = [
        {
            "node_id": n.id,
            "node_type": "Chunk",
            "node_offset": n.node_offset,
            "difficulty": n.difficulty,
        }
        for n in chunks
    ]
    store.add_batch(GRAPH_CHUNKS, [n.id for n in chunks], chunk_embs, chunk_texts, chunk_metas)

    # 2. graph_concepts
    concepts = kg.concepts()
    logger.info("Embedding %d graph concepts", len(concepts))
    concept_texts = []
    for n in concepts:
        ce = kg.concept_entry(n.id)
        primary = ce.primary_term if ce else n.text
        aliases_str = ", ".join(ce.aliases) if ce and ce.aliases else ""
        definition = (ce.definition if ce else "") or n.definition
        text = primary
        if aliases_str:
            text += f" (синонимы: {aliases_str})"
        if definition:
            text += f". {definition}"
        concept_texts.append(text)
    concept_embs = embedder.encode(concept_texts, mode="passage")
    concept_ids = [n.id for n in concepts]
    concept_metas = [
        {"node_id": n.id, "node_type": "Concept", "node_offset": n.node_offset}
        for n in concepts
    ]
    store.add_batch(GRAPH_CONCEPTS, concept_ids, concept_embs, concept_texts, concept_metas)

    # 3. md_chunks
    logger.info("Re-chunking markdown: %s", md_path)
    md_text = md_path.read_text(encoding="utf-8")
    md_chunks = chunk_markdown(
        md_text,
        target_tokens=settings.md_chunk_target_tokens,
        overlap_tokens=settings.md_chunk_overlap_tokens,
    )
    logger.info("md chunks: %d (avg len=%d chars)",
                len(md_chunks),
                int(np.mean([c.char_length for c in md_chunks])) if md_chunks else 0)
    md_texts = [c.text for c in md_chunks]
    md_ids = [c.chunk_id for c in md_chunks]
    md_metas = [c.to_metadata() for c in md_chunks]
    # Embed in batches to keep memory steady
    BATCH = 256
    md_emb_chunks: list[np.ndarray] = []
    for start in range(0, len(md_texts), BATCH):
        batch = md_texts[start : start + BATCH]
        md_emb_chunks.append(embedder.encode(batch, mode="passage"))
        logger.info("md embedded %d/%d", min(start + BATCH, len(md_texts)), len(md_texts))
    md_embs = np.vstack(md_emb_chunks) if md_emb_chunks else np.zeros((0, embedder.dim), dtype=np.float32)
    store.add_batch(MD_CHUNKS, md_ids, md_embs, md_texts, md_metas)

    # 4. Topics: cluster concepts
    logger.info("Clustering concepts into %d topics", settings.n_topics)
    topics_bundle = cluster_concepts(
        kg,
        concept_ids=concept_ids,
        embeddings=concept_embs,
        n_clusters=settings.n_topics,
    )
    save_topics(topics_bundle, topics_path)
    logger.info("Saved topics: %d -> %s", len(topics_bundle.topics), topics_path)

    # 5. Stamp
    _write_stamp(
        data_dir,
        {
            "manifest": manifest_key,
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "counts": {
                "graph_chunks": store.count(GRAPH_CHUNKS),
                "graph_concepts": store.count(GRAPH_CONCEPTS),
                "md_chunks": store.count(MD_CHUNKS),
                "topics": len(topics_bundle.topics),
            },
        },
    )

    summary = {
        "status": "ok",
        "graph_chunks": store.count(GRAPH_CHUNKS),
        "graph_concepts": store.count(GRAPH_CONCEPTS),
        "md_chunks": store.count(MD_CHUNKS),
        "topics": len(topics_bundle.topics),
    }
    logger.info("Ingest done: %s", summary)
    return summary


if __name__ == "__main__":
    force = "--force" in sys.argv
    res = ingest(force=force)
    print(json.dumps(res, ensure_ascii=False))
