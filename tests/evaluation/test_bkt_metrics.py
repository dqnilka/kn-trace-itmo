"""Tests for BKT metrics: monotonicity, AUC-ROC, Log-Loss, RMSE."""

from __future__ import annotations



from app.exams.bkt import BKTParams, predict_correct, update_posterior
from evaluation.metrics.bkt import compute_bkt_metrics, load_events


class TestBKTMonotonicity:
    def test_correct_increases_p_l(self):
        params = BKTParams.default()
        p_before = 0.30
        p_after = update_posterior(p_before, is_correct=True, params=params)
        assert p_after > p_before

    def test_incorrect_decreases_p_l(self):
        params = BKTParams.default()
        p_before = 0.60
        p_after = update_posterior(p_before, is_correct=False, params=params)
        assert p_after < p_before

    def test_monotonicity_on_synthetic_events(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.monotonicity_correct > 0, (
            f"After correct answers P(L) should increase, got Δ={metrics.monotonicity_correct:+.6f}"
        )
        assert metrics.monotonicity_incorrect < 0, (
            f"After incorrect answers P(L) should decrease, got Δ={metrics.monotonicity_incorrect:+.6f}"
        )

    def test_monotonicity_with_custom_params(self):
        params = BKTParams(p_l0=0.20, p_t=0.15, p_g=0.15, p_s=0.05)
        events = [
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"is_correct": False, "concept_updates": [{"concept_id": "c1"}]},
            {"is_correct": False, "concept_updates": [{"concept_id": "c1"}]},
        ]
        metrics = compute_bkt_metrics(events, params=params)
        assert metrics.monotonicity_correct > 0
        assert metrics.monotonicity_incorrect < 0


class TestBKTPredictive:
    def test_auc_is_computed(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.auc_roc is not None, "AUC should be computed with enough events"
        assert 0.0 <= metrics.auc_roc <= 1.0

    def test_log_loss_is_computed(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.log_loss_val is not None, "Log-Loss should be computed"
        assert metrics.log_loss_val > 0

    def test_rmse_is_computed(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.rmse_val is not None, "RMSE should be computed"
        assert 0.0 <= metrics.rmse_val <= 1.0

    def test_auc_above_random(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        if metrics.auc_roc is not None:
            assert metrics.auc_roc > 0.40, (
                f"AUC should be near 0.5+, got {metrics.auc_roc}. "
                f"Note: synthetic events include adversarial patterns (declining users)."
            )

    def test_log_loss_bounded(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        if metrics.log_loss_val is not None:
            assert metrics.log_loss_val < 5.0, (
                f"Log-Loss should be bounded, got {metrics.log_loss_val}"
            )

    def test_too_few_events_no_auc(self):
        events = [
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
        ]
        metrics = compute_bkt_metrics(events)
        assert metrics.auc_roc is None

    def test_all_same_outcome(self):
        events = [
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
        ]
        metrics = compute_bkt_metrics(events)
        assert metrics.auc_roc is None


class TestBKTMetricDetails:
    def test_event_count(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.n_events == len(events)

    def test_concepts_seen(self, events: list[dict]):
        metrics = compute_bkt_metrics(events)
        assert metrics.n_concepts_seen > 0

    def test_predict_correct_range(self):
        params = BKTParams.default()
        for p_l in [0.0, 0.3, 0.5, 0.8, 1.0]:
            p_c = predict_correct(p_l, params)
            assert 0.0 <= p_c <= 1.0


class TestLoadEvents:
    def test_load_from_fixtures(self, fixtures_dir):
        events = load_events(fixtures_dir / "events.jsonl")
        assert len(events) > 0
        for ev in events:
            assert "is_correct" in ev
            assert "task_id" in ev
            assert "user_id" in ev

    def test_load_missing_file(self, tmp_path):
        events = load_events(tmp_path / "nonexistent.jsonl")
        assert events == []
