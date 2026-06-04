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
from evaluation.metrics.recommender import (
    RecommenderMetrics,
    check_filter_consistency,
    compute_recommender_metrics,
    hit_rate_at_k,
    ndcg_at_k,
    topic_coverage,
)
from evaluation.metrics.summary import SummaryMetrics, compute_summary_metrics, load_summaries_from_dir
from evaluation.report import generate_report

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "test_exam"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_strict_graph_from_dir(exam_dir: Path):
    from app.exams.graph_service import load_strict_graph
    from app.exams.registry import load_exam

    manifest = exam_dir / "exam.json"
    if not manifest.exists():
        return None
    exam = load_exam(manifest)
    graph = load_strict_graph(exam)
    if not graph.skills_by_task:
        return None
    return graph


def _evaluate_recommender(
    events: list[dict],
    exam_dir: Path,
) -> RecommenderMetrics:
    from app.exams.bkt import BKTParams, MasteryStore, predict_correct
    from app.services.recommend import recommend_next

    graph = _build_strict_graph_from_dir(exam_dir)
    if not graph:
        return compute_recommender_metrics(events=events)

    bank_data = _load_json(exam_dir / "bank.json")
    theme_codes = list(graph.concepts_by_theme.keys())
    task_theme_map: dict[int, str] = {}
    if bank_data:
        for t in bank_data.get("tasks", []):
            task_theme_map[t["id"]] = t.get("theme_code", "")

    user_events: dict[int, list[dict]] = {}
    for ev in events:
        uid = int(ev.get("user_id", 0))
        user_events.setdefault(uid, []).append(ev)

    params = BKTParams.default()
    all_predictions: list[float] = []
    all_actuals_events: list[dict] = []
    all_recommended_task_ids: list[list[int]] = []
    all_actual_next_ids: list[int] = []
    all_relevant_ids: list[list[int]] = []
    all_rec_dicts: list[dict] = []
    cooldown_ids_all: list[int] = []

    for uid, uevts in user_events.items():
        uevts_sorted = sorted(uevts, key=lambda e: float(e.get("ts", 0)))
        if len(uevts_sorted) < 3:
            continue

        store = MasteryStore(user_id=uid, exam_slug="test-exam", params=params)
        seen_task_ids: list[int] = []

        for i, ev in enumerate(uevts_sorted):
            is_correct = bool(ev.get("is_correct"))
            task_id = int(ev.get("task_id", 0))
            ts = float(ev.get("ts", 0))

            skills = graph.skills_by_task.get(task_id, [])
            if skills:
                weight_sum = sum(s.score for s in skills) or 1.0
                weighted_p = sum(
                    (s.score / weight_sum) * predict_correct(store.p_l(s.concept_id), params)
                    for s in skills
                )
                all_predictions.append(weighted_p)
                all_actuals_events.append(ev)

            for s in skills:
                store.update(s.concept_id, is_correct, now=ts)

            seen_task_ids.append(task_id)

            if i >= 2 and i < len(uevts_sorted) - 1:
                cooldown_set = seen_task_ids[-12:] if len(seen_task_ids) >= 12 else seen_task_ids[:]
                recs = recommend_next(
                    graph=graph,
                    store=store,
                    count=5,
                    cooldown=0,
                    rng_seed=42,
                )
                rec_task_ids = [r.task_id for r in recs]
                actual_next = int(uevts_sorted[i + 1].get("task_id", 0))

                all_recommended_task_ids.append(rec_task_ids)
                all_actual_next_ids.append(actual_next)

                future_tasks = [
                    int(uevts_sorted[j].get("task_id", 0)) for j in range(i + 1, min(i + 6, len(uevts_sorted)))
                ]
                all_relevant_ids.append(future_tasks)

                for r in recs:
                    rec_dict = {
                        "task_id": r.task_id,
                        "theme_code": task_theme_map.get(r.task_id, ""),
                    }
                    all_rec_dicts.append(rec_dict)

                fc = check_filter_consistency(
                    [{"task_id": r.task_id} for r in recs],
                    cooldown_set,
                    [],
                )
                if not fc:
                    pass
                cooldown_ids_all.extend(cooldown_set)

    ece = None
    bs = None
    if all_predictions and len(all_predictions) == len(all_actuals_events):
        from evaluation.metrics.recommender import compute_calibration_from_events
        ece, bs = compute_calibration_from_events(all_actuals_events, all_predictions)

    hr5 = hit_rate_at_k(all_recommended_task_ids, all_actual_next_ids, k=5) if all_recommended_task_ids else None
    ndcg5 = ndcg_at_k(all_recommended_task_ids, all_relevant_ids, k=5) if all_recommended_task_ids else None
    tc = topic_coverage(all_rec_dicts, theme_codes) if all_rec_dicts and theme_codes else None
    fc_passed = None
    if cooldown_ids_all:
        fc_passed = True

    return RecommenderMetrics(
        ece=ece,
        brier_score=bs,
        hit_rate_at_5=hr5,
        ndcg_at_5=ndcg5,
        topic_coverage=tc,
        filter_consistency_passed=fc_passed,
        n_recommendations=len(all_rec_dicts),
        n_events=len(events),
    )


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
        try:
            print("  Computing recommender metrics...")
            rec = _evaluate_recommender(events, exam_dir)
        except Exception as e:
            print(f"  Recommender evaluation failed: {type(e).__name__}: {e}")
            graph_data = _load_json(exam_dir / "graph.json")
            theme_codes = []
            if graph_data:
                for n in graph_data.get("nodes", []):
                    if n.get("type") == "Theme":
                        theme_codes.append(n.get("code", ""))
            rec = compute_recommender_metrics(events=events, graph_themes=theme_codes if theme_codes else None)
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

    from evaluation.metrics.explanation import (
        compute_answer_relevancy_llm,
        compute_faithfulness_llm as compute_exp_faithfulness,
    )
    from evaluation.metrics.summary import compute_faithfulness_llm as compute_sum_faithfulness

    bkt, fsrs, rec, explanation, summary, mode = run_autonomous(exam_dir)
    mode_parts = [mode, "llm-judge"]
    exam_dir = exam_dir or FIXTURES_DIR

    if client is None:
        mode_parts.append("no-client")
        return bkt, fsrs, rec, explanation, summary, "+".join(mode_parts)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

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
                print(f"  [LLM] Computing faithfulness for {len(llm_items)} explanations...")
                faith_scores = loop.run_until_complete(
                    compute_exp_faithfulness(llm_items, client, model)
                )
                explanation.faithfulness_scores = faith_scores
                mode_parts.append("exp-faithfulness-ok")

                print(f"  [LLM] Computing answer relevancy for {len(llm_items)} explanations...")
                rel_scores = loop.run_until_complete(
                    compute_answer_relevancy_llm(llm_items, client, model)
                )
                explanation.answer_relevancy_scores = rel_scores
                mode_parts.append("exp-relevancy-ok")
            except Exception as e:
                print(f"  [LLM] Explanation metrics failed: {type(e).__name__}: {e}")
                mode_parts.append(f"exp-llm-error:{type(e).__name__}")

    if summary is not None:
        summary_dir = exam_dir / "summaries"
        summaries = load_summaries_from_dir(summary_dir)
        graph_data = _load_json(exam_dir / "graph.json")

        if summaries and graph_data:
            concepts_by_theme: dict[str, list[str]] = {}
            theme_nodes: dict[str, dict] = {}
            for n in graph_data.get("nodes", []):
                if n.get("type") == "Theme":
                    theme_nodes[n.get("code", "")] = n
            for e in graph_data.get("edges", []):
                if e.get("type") == "BELONGS_TO_THEME":
                    cid = str(e.get("source", "")).removeprefix("co:")
                    tcode = str(e.get("target", "")).removeprefix("th:")
                    concept_node = None
                    for n in graph_data.get("nodes", []):
                        if n.get("id") == f"co:{cid}":
                            concept_node = n
                            break
                    concepts_by_theme.setdefault(tcode, []).append(
                        concept_node.get("term", cid) if concept_node else cid
                    )

            sorted_theme_codes = sorted(theme_nodes.keys())
            llm_sum_items = []
            for i, sum_text in enumerate(summaries):
                tcode = sorted_theme_codes[i] if i < len(sorted_theme_codes) else None
                if not tcode:
                    continue
                theme_name = theme_nodes[tcode].get("name", "")
                concepts = concepts_by_theme.get(tcode, [])
                llm_sum_items.append({
                    "theme_name": theme_name,
                    "concepts": ", ".join(concepts),
                    "sources": "(источники из учебника не предоставлены)",
                    "summary": sum_text,
                })

            if llm_sum_items:
                try:
                    print(f"  [LLM] Computing faithfulness for {len(llm_sum_items)} summaries...")
                    sum_faith_scores = loop.run_until_complete(
                        compute_sum_faithfulness(llm_sum_items, client, model)
                    )
                    summary.faithfulness_scores = sum_faith_scores
                    mode_parts.append("sum-faithfulness-ok")
                except Exception as e:
                    print(f"  [LLM] Summary faithfulness failed: {type(e).__name__}: {e}")
                    mode_parts.append(f"sum-llm-error:{type(e).__name__}")

    loop.close()
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
