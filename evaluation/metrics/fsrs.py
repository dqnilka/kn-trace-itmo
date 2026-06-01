"""FSRS-lite quality metrics.

Measures:
  - Stability monotonicity: S increases on correct, decreases on incorrect
  - Calibration: ECE of retrievability vs actual recall
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.exams.bkt import (
    INITIAL_STABILITY_WRONG,
    _next_stability,
    retrievability,
)


@dataclass
class FSRSMetrics:
    stability_monotonicity_correct: float
    stability_monotonicity_incorrect: float
    calibration_ece: float | None
    n_events: int


def _replay_fsrs(
    events: list[dict],
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Replay events through FSRS, collecting stability changes and retrievability.

    Returns (delta_s_correct, delta_s_incorrect, retrievabilities, actuals).
    """
    concept_stability: dict[str, float] = {}
    concept_last_seen: dict[str, float] = {}

    delta_s_correct: list[float] = []
    delta_s_incorrect: list[float] = []
    retrievabilities: list[float] = []
    actuals: list[float] = []

    for ev in events:
        is_correct = bool(ev.get("is_correct", False))
        ts = float(ev.get("ts", 0))
        concept_updates = ev.get("concept_updates") or []

        for cu in concept_updates:
            cid = cu.get("concept_id", "")
            if not cid:
                continue

            prev_s = concept_stability.get(cid, 0.0)
            prev_seen = concept_last_seen.get(cid, 0.0)

            if prev_s > 0 and prev_seen > 0:
                r_now = retrievability(prev_s, prev_seen, ts)
                retrievabilities.append(r_now)
                actuals.append(1.0 if is_correct else 0.0)

            new_s = _next_stability(prev_s, retrievability(prev_s, prev_seen, ts), is_correct)
            delta = new_s - prev_s if prev_s > 0 else (new_s - INITIAL_STABILITY_WRONG)

            if is_correct:
                delta_s_correct.append(delta)
            else:
                delta_s_incorrect.append(delta)

            concept_stability[cid] = new_s
            concept_last_seen[cid] = ts

    return delta_s_correct, delta_s_incorrect, retrievabilities, actuals


def compute_ece(
    predictions: list[float],
    actuals: list[float],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error.

    ECE = sum(|avg_predicted - avg_actual| * n_bucket) / n_total
    """
    if not predictions or len(predictions) != len(actuals):
        return 0.0

    n = len(predictions)
    bin_size = n / n_bins
    ece = 0.0

    for i in range(n_bins):
        start = int(i * bin_size)
        end = int((i + 1) * bin_size) if i < n_bins - 1 else n
        if start >= end:
            continue
        bin_preds = predictions[start:end]
        bin_actuals = actuals[start:end]
        avg_pred = float(np.mean(bin_preds))
        avg_actual = float(np.mean(bin_actuals))
        ece += abs(avg_pred - avg_actual) * (end - start)

    return round(ece / n, 6)


def compute_fsrs_metrics(events: list[dict]) -> FSRSMetrics:
    """Compute all FSRS quality metrics from event history."""
    delta_s_correct, delta_s_incorrect, retrievabilities, actuals = _replay_fsrs(events)

    mono_correct = float(np.mean(delta_s_correct)) if delta_s_correct else 0.0
    mono_incorrect = float(np.mean(delta_s_incorrect)) if delta_s_incorrect else 0.0

    ece = None
    if len(retrievabilities) >= 10:
        sorted_pairs = sorted(zip(retrievabilities, actuals))
        sorted_preds = [p for p, _ in sorted_pairs]
        sorted_acts = [a for _, a in sorted_pairs]
        ece = compute_ece(sorted_preds, sorted_acts)

    return FSRSMetrics(
        stability_monotonicity_correct=round(mono_correct, 2),
        stability_monotonicity_incorrect=round(mono_incorrect, 2),
        calibration_ece=ece,
        n_events=len(events),
    )
