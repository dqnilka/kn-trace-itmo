"""BKT (Bayesian Knowledge Tracing) quality metrics.

Measures:
  - Monotonicity: P(L) increases on correct, decreases on incorrect
  - Predictive quality: AUC-ROC, Log-Loss, RMSE of P(correct) vs actual outcome
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.metrics import log_loss, roc_auc_score

from app.exams.bkt import BKTParams, predict_correct, update_posterior


@dataclass
class BKTMetrics:
    monotonicity_correct: float
    monotonicity_incorrect: float
    auc_roc: float | None
    log_loss_val: float | None
    rmse_val: float | None
    n_events: int
    n_concepts_seen: int


def _replay_events(
    events: list[dict],
    params: BKTParams | None = None,
) -> tuple[list[float], list[bool], list[tuple[float, float]], list[tuple[float, float]]]:
    """Replay events through BKT, collecting predictions and delta-P values.

    Returns (predictions, actuals, delta_p_correct, delta_p_incorrect).
    """
    if params is None:
        params = BKTParams.default()

    concept_state: dict[str, float] = {}
    predictions: list[float] = []
    actuals: list[bool] = []
    delta_correct: list[tuple[float, float]] = []
    delta_incorrect: list[tuple[float, float]] = []

    for ev in events:
        is_correct = bool(ev.get("is_correct", False))
        concept_updates = ev.get("concept_updates") or []

        for cu in concept_updates:
            cid = cu.get("concept_id", "")
            if not cid:
                continue
            p_before = concept_state.get(cid, params.p_l0)
            p_correct_before = predict_correct(p_before, params)
            predictions.append(float(p_correct_before))
            actuals.append(is_correct)

            p_after = update_posterior(p_before, is_correct, params)
            delta = p_after - p_before

            if is_correct:
                delta_correct.append((delta, p_before))
            else:
                delta_incorrect.append((delta, p_before))

            concept_state[cid] = p_after

    return predictions, actuals, delta_correct, delta_incorrect


def compute_bkt_metrics(
    events: list[dict],
    params: BKTParams | None = None,
) -> BKTMetrics:
    """Compute all BKT quality metrics from event history."""
    predictions, actuals, delta_correct, delta_incorrect = _replay_events(events, params)

    mono_correct = (
        float(np.mean([d[0] for d in delta_correct])) if delta_correct else 0.0
    )
    mono_incorrect = (
        float(np.mean([d[0] for d in delta_incorrect])) if delta_incorrect else 0.0
    )

    auc = None
    ll = None
    rmse = None

    if len(set(actuals)) >= 2 and len(predictions) >= 10:
        try:
            auc = float(roc_auc_score(actuals, predictions))
        except ValueError:
            pass
        try:
            eps = 1e-15
            p_clipped = np.clip(predictions, eps, 1.0 - eps)
            ll = float(log_loss(actuals, p_clipped))
        except ValueError:
            pass
        rmse = float(np.sqrt(np.mean((np.array(predictions) - np.array(actuals)) ** 2)))

    concept_ids_seen: set[str] = set()
    for ev in events:
        for cu in ev.get("concept_updates") or []:
            concept_ids_seen.add(cu.get("concept_id", ""))

    return BKTMetrics(
        monotonicity_correct=round(mono_correct, 6),
        monotonicity_incorrect=round(mono_incorrect, 6),
        auc_roc=round(auc, 4) if auc is not None else None,
        log_loss_val=round(ll, 4) if ll is not None else None,
        rmse_val=round(rmse, 4) if rmse is not None else None,
        n_events=len(events),
        n_concepts_seen=len(concept_ids_seen),
    )


def load_events(events_path: Path) -> list[dict]:
    """Load events from JSONL file."""
    if not events_path.exists():
        return []
    events: list[dict] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events
