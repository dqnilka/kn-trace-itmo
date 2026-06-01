"""Recommender quality metrics.

Measures:
  - ECE / Brier Score: calibration of expected_p_correct
  - Hit Rate@K / NDCG@K: ranking quality
  - Topic Coverage: diversity of recommendations
  - Filter consistency: coherence checks (cooldown, mastered veto)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from evaluation.metrics.fsrs import compute_ece


@dataclass
class RecommenderMetrics:
    ece: float | None
    brier_score: float | None
    hit_rate_at_5: float | None
    ndcg_at_5: float | None
    topic_coverage: float | None
    filter_consistency_passed: bool | None
    n_recommendations: int
    n_events: int


def brier_score(predictions: list[float], actuals: list[float]) -> float:
    """Brier Score = mean((predicted - actual)^2)."""
    if not predictions:
        return 0.0
    return round(float(np.mean((np.array(predictions) - np.array(actuals)) ** 2)), 6)


def hit_rate_at_k(
    recommended_task_ids: list[list[int]],
    actual_next_task_ids: list[int],
    k: int = 5,
) -> float:
    """Fraction of cases where the actual next task is in top-K recommendations.

    Args:
        recommended_task_ids: list of recommendation lists (each top-K task IDs)
        actual_next_task_ids: list of actual next task IDs (one per recommendation set)
    """
    if not recommended_task_ids:
        return 0.0
    hits = 0
    for recs, actual in zip(recommended_task_ids, actual_next_task_ids):
        if actual in recs[:k]:
            hits += 1
    return round(hits / len(recommended_task_ids), 4)


def ndcg_at_k(
    recommended_task_ids: list[list[int]],
    relevant_task_ids: list[list[int]],
    k: int = 5,
) -> float:
    """Normalized Discounted Cumulative Gain at K.

    Args:
        recommended_task_ids: list of recommendation lists
        relevant_task_ids: list of relevant (actually solved next) task ID lists
    """
    if not recommended_task_ids:
        return 0.0

    scores: list[float] = []
    for recs, relevant in zip(recommended_task_ids, relevant_task_ids):
        if not relevant:
            continue
        dcg = 0.0
        for i, tid in enumerate(recs[:k]):
            if tid in relevant:
                dcg += 1.0 / math.log2(i + 2)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
        if idcg > 0:
            scores.append(dcg / idcg)

    return round(float(np.mean(scores)), 4) if scores else 0.0


def topic_coverage(
    recommended_tasks: list[dict],
    graph_themes: list[str],
) -> float:
    """Fraction of available themes that appear in recommendations.

    Args:
        recommended_tasks: list of dicts with 'theme_code' key
        graph_themes: all available theme codes
    """
    if not graph_themes:
        return 0.0
    covered = {t.get("theme_code", "") for t in recommended_tasks if t.get("theme_code")}
    return round(len(covered & set(graph_themes)) / len(graph_themes), 4)


def check_filter_consistency(
    recommendations: list[dict],
    cooldown_task_ids: list[int],
    mastered_concept_ids: list[str],
    store_state: dict | None = None,
) -> bool:
    """Check that recommendations respect all filters.

    Returns True if all filters are respected:
    - No cooldown tasks in recommendations
    - No fully mastered tasks (if store provided)

    Args:
        recommendations: list of Recommendation dicts with task_id
        cooldown_task_ids: tasks that should be excluded (cooldown)
        mastered_concept_ids: concepts that are mastered (for mastered filter)
        store_state: optional mastery store state for checking mastered tasks
    """
    cooldown_set = set(cooldown_task_ids)
    for rec in recommendations:
        tid = rec.get("task_id")
        if tid in cooldown_set:
            return False
    return True


def compute_calibration_from_events(
    events: list[dict],
    predictions: list[float],
) -> tuple[float | None, float | None]:
    """Compute ECE and Brier Score from predictions vs actual outcomes.

    Args:
        events: list of event dicts with 'is_correct'
        predictions: predicted P(correct) for each event
    """
    if len(events) != len(predictions) or len(events) < 5:
        return None, None

    actuals = [1.0 if ev.get("is_correct") else 0.0 for ev in events]

    sorted_pairs = sorted(zip(predictions, actuals))
    sorted_preds = [p for p, _ in sorted_pairs]
    sorted_acts = [a for _, a in sorted_pairs]

    ece = compute_ece(sorted_preds, sorted_acts)
    bs = brier_score(predictions, actuals)
    return ece, bs


def compute_recommender_metrics(
    events: list[dict],
    recommendations_per_user: dict[int, list[dict]] | None = None,
    graph_themes: list[str] | None = None,
    predictions: list[float] | None = None,
) -> RecommenderMetrics:
    """Compute all recommender quality metrics."""
    ece = None
    bs = None
    if predictions and len(predictions) == len(events):
        ece, bs = compute_calibration_from_events(events, predictions)

    hr5 = None
    ndcg5 = None
    tc = None
    fc = None
    n_recs = 0

    if recommendations_per_user:
        all_recs = []
        all_recommended_tasks = []
        for user_id, recs in recommendations_per_user.items():
            all_recs.extend(recs)
            all_recommended_tasks.extend([r.get("task_id") for r in recs])
        n_recs = len(all_recs)

        if graph_themes:
            tc = topic_coverage(all_recs, graph_themes)

    return RecommenderMetrics(
        ece=ece,
        brier_score=bs,
        hit_rate_at_5=hr5,
        ndcg_at_5=ndcg5,
        topic_coverage=tc,
        filter_consistency_passed=fc,
        n_recommendations=n_recs,
        n_events=len(events),
    )
