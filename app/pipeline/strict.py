"""Strict-mode pipeline orchestrator for a single exam.

What it does:
  1. Load exam manifest + bank.json + ConceptDictionary.json (k2-18 step 2 reuse).
  2. Link bank tasks to concepts by embedding similarity (top-K per task).
  3. Assemble a unified graph.json:
       Chapter / Theme / Task / Concept nodes
       HAS_THEME, HAS_TASK, TESTS_CONCEPT, BELONGS_TO_THEME edges
  4. Persist task_skills.jsonl + graph.json under the exam dir.

What it does NOT do (yet):
  - LLM extraction of prereq edges (planned next).
  - MD section → theme mapping (planned next).
  - Re-running k2-18 step 1 (slicing) — we reuse staging/*.json if present.

Run::

    docker compose run --rm api python -m app.pipeline.strict \\
        --exam fsfr-basic [--limit N] [--top-k 3] [--min-score 0.35]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.exams.registry import ExamRegistry, UnknownExamError, load_bank
from app.pipeline.link_tasks_to_concepts import (
    TaskConceptLink,
    link_tasks_to_concepts,
    save_links_jsonl,
)
from app.pipeline.extract_prerequisites import ConceptPrereqLink, extract_prerequisites
from app.pipeline.link_theory_to_themes import (
    link_theory_to_themes,
    save_theme_sections,
)
from app.pipeline.llm_link import llm_rerank
from app.rag.embeddings import E5Embedder
from app.rag.generator import Generator
from app.rag.vectorstore import VectorStore

logger = get_logger(__name__)


def load_concept_dictionary(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning("ConceptDictionary not found at %s — emitting empty list", path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("concepts") or [])


def assemble_graph(
    *,
    bank: dict,
    concepts: list[dict],
    links: list[TaskConceptLink],
    prereqs: list[ConceptPrereqLink] | None = None,
) -> dict:
    """Build the unified graph.json described in AS_IS_TO_BE.md §2.4."""
    chapters = bank.get("chapters", [])
    themes = bank.get("themes", [])
    tasks = bank.get("tasks", [])
    chapter_by_id = {int(c["id"]): c for c in chapters}
    theme_by_code = {str(t["code"]): t for t in themes}

    nodes: list[dict] = []
    edges: list[dict] = []

    # --- Chapter / Theme / Task nodes ---
    for c in chapters:
        nodes.append(
            {
                "id": f"ch:{c['id']}",
                "type": "Chapter",
                "num": c.get("num"),
                "name": c.get("name"),
            }
        )
    for t in themes:
        nodes.append(
            {
                "id": f"th:{t['code']}",
                "type": "Theme",
                "chapter_id": t.get("chapter_id"),
                "code": t.get("code"),
                "name": t.get("name"),
            }
        )
        edges.append(
            {
                "source": f"ch:{t['chapter_id']}",
                "target": f"th:{t['code']}",
                "type": "HAS_THEME",
            }
        )
    for tk in tasks:
        nodes.append(
            {
                "id": f"tk:{tk['id']}",
                "type": "Task",
                "theme_code": tk.get("theme_code"),
                "task_number": tk.get("task_number"),
                "task_text": tk.get("task_text"),
                "answer_type": tk.get("answer_type"),
                "difficulty_prior": tk.get("difficulty"),
                "options": tk.get("options", []),
            }
        )
        edges.append(
            {
                "source": f"th:{tk['theme_code']}",
                "target": f"tk:{tk['id']}",
                "type": "HAS_TASK",
            }
        )

    # --- Concept nodes (only those referenced by at least one link) ---
    used_concepts: set[str] = {l.concept_id for l in links}
    by_concept = {c.get("concept_id") or c.get("id"): c for c in concepts}
    for cid in used_concepts:
        c = by_concept.get(cid)
        if not c:
            continue
        term = c.get("term") or {}
        primary = (
            term.get("primary") if isinstance(term, dict) else None
        ) or c.get("term_primary") or cid
        aliases = (term.get("aliases") if isinstance(term, dict) else None) or []
        nodes.append(
            {
                "id": f"co:{cid}",
                "type": "Concept",
                "term": primary,
                "aliases": aliases,
                "definition": c.get("definition", ""),
            }
        )

    # --- TESTS_CONCEPT edges ---
    for l in links:
        edges.append(
            {
                "source": f"tk:{l.task_id}",
                "target": f"co:{l.concept_id}",
                "type": "TESTS_CONCEPT",
                "weight": l.score,
            }
        )

    # --- BELONGS_TO_THEME edges: concept ↔ majority theme of its linked tasks ---
    concept_theme_votes: dict[str, Counter] = {}
    task_by_id = {int(t["id"]): t for t in tasks}
    for l in links:
        task = task_by_id.get(l.task_id)
        if not task:
            continue
        votes = concept_theme_votes.setdefault(l.concept_id, Counter())
        votes[str(task.get("theme_code"))] += 1
    for cid, votes in concept_theme_votes.items():
        top_theme, _ = votes.most_common(1)[0]
        if top_theme in theme_by_code:
            edges.append(
                {
                    "source": f"co:{cid}",
                    "target": f"th:{top_theme}",
                    "type": "BELONGS_TO_THEME",
                    "weight": 1.0,
                }
            )

    # --- PREREQUISITE edges between concepts (optional, from LLM) ---
    if prereqs:
        seen_pairs: set[tuple[str, str]] = set()
        for p in prereqs:
            key = (p.from_concept_id, p.to_concept_id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            edges.append(
                {
                    "source": f"co:{p.from_concept_id}",
                    "target": f"co:{p.to_concept_id}",
                    "type": "PREREQUISITE",
                    "weight": p.score,
                    "chapter_id": p.chapter_id,
                    "reason": p.reason,
                }
            )

    node_counts = Counter(n["type"] for n in nodes)
    edge_counts = Counter(e["type"] for e in edges)
    return {
        "_meta": {
            "exam_slug": bank.get("_meta", {}).get("source_file"),
            "version": bank.get("_meta", {}).get("generated_at"),
            "pipeline_mode": "strict",
            "stats": {
                "nodes": len(nodes),
                "edges": len(edges),
                "by_node_type": dict(node_counts),
                "by_edge_type": dict(edge_counts),
                "linked_concepts": len(used_concepts),
            },
        },
        "nodes": nodes,
        "edges": edges,
    }


def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    registry = ExamRegistry(settings.exams_dir)
    try:
        exam = registry.get(args.exam)
    except UnknownExamError:
        logger.error("Unknown exam slug: %s (looked in %s)", args.exam, settings.exams_dir)
        return 2

    logger.info("Strict pipeline starting for exam %s (root=%s)", exam.slug, exam.root)
    started = time.time()

    bank = load_bank(exam)
    tasks: list[dict] = bank.get("tasks", [])
    themes_by_code = {str(t["code"]): t for t in bank.get("themes", [])}
    if args.limit:
        tasks = tasks[: args.limit]
        logger.info("Limiting tasks to first %d", len(tasks))

    concepts_path = Path(args.concepts_path) if args.concepts_path else settings.concept_dict_path
    concepts = load_concept_dictionary(concepts_path)
    logger.info("Loaded %d concepts from %s", len(concepts), concepts_path)

    logger.info("Initializing embedder %s ...", settings.embedding_model)
    embedder = E5Embedder(model_name=settings.embedding_model)

    candidate_top_k = max(args.top_k, args.llm_top_k) if args.llm_rerank else args.top_k
    candidates = link_tasks_to_concepts(
        tasks=tasks,
        themes_by_code=themes_by_code,
        concepts=concepts,
        embedder=embedder,
        top_k=candidate_top_k,
        min_score=args.min_score,
    )
    logger.info(
        "Embedding step: %d candidate task↔concept pairs (top_k=%d)",
        len(candidates), candidate_top_k,
    )

    if args.llm_rerank:
        from collections import defaultdict
        cand_by_task: dict[int, list[TaskConceptLink]] = defaultdict(list)
        for c in candidates:
            cand_by_task[c.task_id].append(c)
        logger.info("LLM rerank: starting (model=%s, batch=%d)", settings.llm_model, args.llm_batch)
        generator = Generator.from_settings()
        links, llm_usage = llm_rerank(
            tasks=tasks,
            candidates_by_task=dict(cand_by_task),
            llm_generator=generator,
            batch_size=args.llm_batch,
        )
        logger.info(
            "LLM rerank produced %d final task↔concept links (was %d candidates)",
            len(links), len(candidates),
        )
    else:
        links = candidates
    logger.info("Produced %d task→concept links", len(links))

    # Build prereqs AFTER we have task↔concept links, so concept-to-chapter
    # assignment is fresh. We pass a draft graph (without prereqs yet) into the
    # extractor.
    prereqs: list[ConceptPrereqLink] = []
    if args.extract_prereqs:
        logger.info("PREREQUISITE extraction: starting (model=%s)", settings.llm_model)
        draft = assemble_graph(bank=bank, concepts=concepts, links=links)
        generator = Generator.from_settings()
        prereqs, prereq_usage = extract_prerequisites(
            graph=draft,
            llm_generator=generator,
        )
        logger.info(
            "PREREQUISITE extraction: %d edges across %d chapters (~%d tokens in / %d out, %.1fs)",
            len(prereqs),
            len({p.chapter_id for p in prereqs}),
            prereq_usage.input_tokens,
            prereq_usage.output_tokens,
            prereq_usage.elapsed_s,
        )

    out_dir = exam.root
    out_dir.mkdir(parents=True, exist_ok=True)
    links_path = out_dir / "task_skills.jsonl"
    n = save_links_jsonl(links, links_path)
    logger.info("Wrote %d links to %s", n, links_path)

    graph = assemble_graph(bank=bank, concepts=concepts, links=links, prereqs=prereqs)

    # --- theory → theme mapping (offline RAG pre-rank) ---
    if args.link_theory:
        logger.info("Linking MD sections to themes…")
        store = VectorStore(persist_dir=settings.chroma_path)
        ts_links, ts_meta = link_theory_to_themes(
            graph=graph,
            bank=bank,
            embedder=embedder,
            store=store,
            top_n=args.theory_top_n,
            min_score=args.theory_min_score,
        )
        save_theme_sections(ts_links, out_dir / "theme_sections.json", ts_meta)
        logger.info(
            "theme_sections.json: %d links over %d themes",
            len(ts_links), ts_meta.get("themes_covered", 0),
        )

    graph_path = out_dir / "graph.json"
    # Backup the previous graph so accidental `--limit N` smoke runs don't
    # wipe a hard-earned full graph. Last 3 backups kept.
    if graph_path.exists():
        from time import strftime
        ts = strftime("%Y%m%d-%H%M%S")
        backup_dir = out_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        graph_path.rename(backup_dir / f"graph.{ts}.json")
        # prune to last 3 backups
        backups = sorted(backup_dir.glob("graph.*.json"))
        for old in backups[:-3]:
            old.unlink(missing_ok=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote graph to %s (%s)", graph_path, _human_size(graph_path.stat().st_size))

    elapsed = time.time() - started
    print(json.dumps(
        {
            "exam": exam.slug,
            "duration_s": round(elapsed, 1),
            "tasks_processed": len(tasks),
            "concepts_available": len(concepts),
            "links_total": n,
            "graph_stats": graph["_meta"]["stats"],
            "outputs": {
                "task_skills": str(links_path),
                "graph": str(graph_path),
            },
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def _human_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    return f"{b/(1024*1024):.1f} MB"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.pipeline.strict",
        description="Strict-mode pipeline: bank + concepts → unified graph.",
    )
    p.add_argument("--exam", required=True, help="Exam slug (e.g. fsfr-basic)")
    p.add_argument("--limit", type=int, default=0, help="Process only first N tasks (debug)")
    p.add_argument("--top-k", type=int, default=3, help="Concept candidates per task (final, when no LLM rerank)")
    p.add_argument("--min-score", type=float, default=0.35, help="Min cosine similarity to keep a link")
    p.add_argument(
        "--llm-rerank",
        action="store_true",
        help="Use GPT to rerank embedding candidates (higher quality, ~15 min on full FSFR)",
    )
    p.add_argument(
        "--llm-top-k",
        type=int,
        default=10,
        help="How many candidates to pass to the LLM for reranking (per task)",
    )
    p.add_argument(
        "--llm-batch",
        type=int,
        default=10,
        help="Tasks per LLM request (lower=more requests, higher=more tokens per request)",
    )
    p.add_argument(
        "--extract-prereqs",
        action="store_true",
        help="Extract PREREQUISITE edges between concepts via LLM (one request per chapter)",
    )
    p.add_argument(
        "--link-theory",
        action="store_true",
        help="Build theme → MD-section ranking (writes theme_sections.json)",
    )
    p.add_argument("--theory-top-n", type=int, default=6, help="Top MD sections per theme")
    p.add_argument("--theory-min-score", type=float, default=0.35, help="Cosine threshold for sections")
    p.add_argument(
        "--concepts-path",
        type=str,
        default=None,
        help="Override ConceptDictionary.json path (default: settings.concept_dict_path)",
    )
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(run(args))
