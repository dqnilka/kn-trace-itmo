"""Evaluation runner — main entry point.

Runs all quality metrics and generates a markdown report.
Usage: python -m evaluation.runner [--output PATH] [--exam-dir PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.metrics.bkt import BKTMetrics, compute_bkt_metrics, load_events
from evaluation.metrics.explanation import (
    ExplanationMetrics,
    compute_explanation_metrics,
    load_explanations_from_dir,
)
from evaluation.metrics.fsrs import FSRSMetrics, compute_fsrs_metrics
from evaluation.metrics.recommender import RecommenderMetrics, compute_recommender_metrics
from evaluation.metrics.summary import SummaryMetrics, compute_summary_metrics, load_summaries_from_dir
from evaluation.report import generate_report

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "test_exam"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_autonomous(
    exam_dir: Path | None = None,
) -> tuple[BKTMetrics | None, FSRSMetrics | None, RecommenderMetrics | None, ExplanationMetrics | None, SummaryMetrics | None, str]:
    """Run all autonomous (no LLM) metrics.

    Returns (bkt, fsrs, recommender, explanation, summary, mode_str).
    """
    exam_dir = exam_dir or FIXTURES_DIR
    mode_parts = ["autonomous"]

    events = load_events(exam_dir / "events.jsonl")
    bkt = None
    fsrs = None
    rec = None

    if events:
        bkt = compute_bkt_metrics(events)
        fsrs = compute_fsrs_metrics(events)

        graph_data = _load_json(exam_dir / "graph.json")
        theme_codes = []
        if graph_data:
            for n in graph_data.get("nodes", []):
                if n.get("type") == "Theme":
                    theme_codes.append(n.get("code", ""))
        rec = compute_recommender_metrics(
            events=events,
            graph_themes=theme_codes if theme_codes else None,
        )
    else:
        mode_parts.append("no-events")

    explanation_dir = exam_dir / "explanations"
    explanation = None
    if explanation_dir.exists():
        explanations = load_explanations_from_dir(explanation_dir)
        if explanations:
            explanation = compute_explanation_metrics(explanations)
    else:
        mode_parts.append("no-explanations")

    summary_dir = exam_dir / "summaries"
    summary = None
    if summary_dir.exists():
        summaries = load_summaries_from_dir(summary_dir)
        if summaries:
            graph_data = _load_json(exam_dir / "graph.json")
            concepts_by_theme: dict[str, list[str]] = {}
            theme_names: list[str] = []
            if graph_data:
                for e in graph_data.get("edges", []):
                    if e.get("type") == "BELONGS_TO_THEME":
                        cid = str(e.get("source", "")).removeprefix("co:")
                        tcode = str(e.get("target", "")).removeprefix("th:")
                        concepts_by_theme.setdefault(tcode, []).append(cid)
                for n in graph_data.get("nodes", []):
                    if n.get("type") == "Theme":
                        theme_names.append(n.get("code", ""))

            summary = compute_summary_metrics(
                summaries,
                concepts_per_theme=concepts_by_theme if concepts_by_theme else None,
                theme_names=theme_names if theme_names else None,
            )
    else:
        mode_parts.append("no-summaries")

    return bkt, fsrs, rec, explanation, summary, "+".join(mode_parts)


def run_with_llm(
    exam_dir: Path | None = None,
    client: object = None,
    model: str = "gpt-4o-mini",
) -> tuple[BKTMetrics | None, FSRSMetrics | None, RecommenderMetrics | None, ExplanationMetrics | None, SummaryMetrics | None, str]:
    """Run all metrics including LLM-as-judge.

    Returns same tuple as run_autonomous.
    """
    import asyncio

    bkt, fsrs, rec, explanation, summary, mode = run_autonomous(exam_dir)
    mode_parts = [mode, "llm-judge"]
    exam_dir = exam_dir or FIXTURES_DIR

    if client is None:
        mode_parts.append("no-client")
        return bkt, fsrs, rec, explanation, summary, "+".join(mode_parts)

    bank_data = _load_json(exam_dir / "bank.json")

    if explanation is not None and bank_data:
        explanation_dir = exam_dir / "explanations"
        explanations = load_explanations_from_dir(explanation_dir)
        tasks_by_id = {t["id"]: t for t in bank_data.get("tasks", [])}

        llm_items = []
        for i, exp_text in enumerate(explanations):
            task = tasks_by_id.get(i + 1)
            if not task:
                continue
            correct_opt = next((o for o in task.get("options", []) if o.get("is_correct")), None)
            llm_items.append({
                "question": task.get("task_text", ""),
                "correct_answer": (correct_opt or {}).get("text", ""),
                "picked_answer": "",
                "context": "",
                "explanation": exp_text,
            })

        if llm_items:
            try:
                faith_scores = asyncio.get_event_loop().run_until_complete(
                    __import__("evaluation.metrics.explanation", fromlist=["compute_faithfulness_llm"])
                    .compute_faithliness_llm(llm_items, client, model)
                )
                explanation.faithfulness_scores = faith_scores

                rel_scores = asyncio.get_event_loop().run_until_complete(
                    __import__("evaluation.metrics.explanation", fromlist=["compute_answer_relevancy_llm"])
                    .compute_answer_relevancy_llm(llm_items, client, model)
                )
                explanation.answer_relevancy_scores = rel_scores
            except Exception as e:
                mode_parts.append(f"llm-error:{e}")

    return bkt, fsrs, rec, explanation, summary, "+".join(mode_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality evaluation runner")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("evaluation_report.md"),
        help="Output .md file path (default: evaluation_report.md)",
    )
    parser.add_argument(
        "--exam-dir",
        type=Path,
        default=None,
        help="Path to exam directory with data files (default: evaluation/fixtures/test_exam)",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        default=False,
        help="Run LLM-as-judge metrics (requires LLM_API_KEY)",
    )
    args = parser.parse_args()

    exam_dir = args.exam_dir or FIXTURES_DIR

    if args.with_llm:
        try:
            from app.core.config import get_settings
            settings = get_settings()
            if settings.effective_api_key:
                from openai import OpenAI
                client = OpenAI(
                    api_key=settings.effective_api_key,
                    base_url=settings.llm_base_url,
                )
                bkt, fsrs, rec, explanation, summary, mode = run_with_llm(
                    exam_dir, client=client, model=settings.llm_model,
                )
            else:
                print("Warning: LLM_API_KEY not set, running autonomous mode only")
                bkt, fsrs, rec, explanation, summary, mode = run_autonomous(exam_dir)
        except Exception as e:
            print(f"Warning: LLM setup failed ({e}), running autonomous mode only")
            bkt, fsrs, rec, explanation, summary, mode = run_autonomous(exam_dir)
    else:
        bkt, fsrs, rec, explanation, summary, mode = run_autonomous(exam_dir)

    exam_slug = "unknown"
    manifest = _load_json(exam_dir / "exam.json")
    if manifest:
        exam_slug = manifest.get("slug", "unknown")

    report = generate_report(
        bkt=bkt,
        fsrs=fsrs,
        recommender=rec,
        explanation=explanation,
        summary=summary,
        exam_slug=exam_slug,
        mode=mode,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Report saved to {args.output}")
    print(f"Mode: {mode}")

    if bkt:
        print(f"BKT: AUC={bkt.auc_roc}, mono_correct={bkt.monotonicity_correct:+.6f}")
    if fsrs:
        print(f"FSRS: ECE={fsrs.calibration_ece}, mono_S_correct={fsrs.stability_monotonicity_correct:+.2f}")
    if explanation:
        print(f"Explanation: structure={explanation.structure_compliance}")
    if summary:
        print(f"Summary: format={summary.format_compliance}")


if __name__ == "__main__":
    main()
