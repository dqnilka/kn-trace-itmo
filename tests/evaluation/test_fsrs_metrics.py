"""Tests for FSRS metrics: stability monotonicity, calibration ECE."""

from __future__ import annotations


from evaluation.metrics.fsrs import compute_ece, compute_fsrs_metrics


class TestFSRSMonotonicity:
    def test_correct_increases_stability(self, events: list[dict]):
        metrics = compute_fsrs_metrics(events)
        assert metrics.stability_monotonicity_correct > 0, (
            f"Stability should increase after correct answers, got Δ={metrics.stability_monotonicity_correct:+.2f}"
        )

    def test_incorrect_decreases_stability(self, events: list[dict]):
        metrics = compute_fsrs_metrics(events)
        assert metrics.stability_monotonicity_incorrect < 0, (
            f"Stability should decrease after incorrect answers, got Δ={metrics.stability_monotonicity_incorrect:+.2f}"
        )

    def test_monotonicity_with_single_sequence(self):
        events = [
            {"ts": 100.0, "is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"ts": 200.0, "is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"ts": 300.0, "is_correct": False, "concept_updates": [{"concept_id": "c1"}]},
            {"ts": 400.0, "is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
        ]
        metrics = compute_fsrs_metrics(events)
        assert metrics.stability_monotonicity_correct > 0
        assert metrics.stability_monotonicity_incorrect < 0


class TestFSRSCalibration:
    def test_ece_is_computed(self, events: list[dict]):
        metrics = compute_fsrs_metrics(events)
        if metrics.calibration_ece is not None:
            assert 0.0 <= metrics.calibration_ece <= 1.0

    def test_ece_perfect_calibration(self):
        predictions = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]
        actuals = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        ece = compute_ece(predictions, actuals, n_bins=4)
        assert ece < 0.3

    def test_ece_worst_calibration(self):
        predictions = [0.9, 0.9, 0.9, 0.9, 0.9]
        actuals = [0.0, 0.0, 0.0, 0.0, 0.0]
        ece = compute_ece(predictions, actuals, n_bins=5)
        assert ece > 0.5

    def test_ece_empty(self):
        assert compute_ece([], []) == 0.0

    def test_ece_mismatched_lengths(self):
        assert compute_ece([0.5, 0.5], [1.0]) == 0.0


class TestFSRSMetricDetails:
    def test_event_count(self, events: list[dict]):
        metrics = compute_fsrs_metrics(events)
        assert metrics.n_events == len(events)

    def test_multiple_concepts(self):
        events = [
            {"ts": 100.0, "is_correct": True, "concept_updates": [{"concept_id": "c1"}]},
            {"ts": 200.0, "is_correct": True, "concept_updates": [{"concept_id": "c2"}]},
            {"ts": 300.0, "is_correct": False, "concept_updates": [{"concept_id": "c1"}]},
            {"ts": 400.0, "is_correct": False, "concept_updates": [{"concept_id": "c2"}]},
        ]
        metrics = compute_fsrs_metrics(events)
        assert metrics.stability_monotonicity_correct > 0
        assert metrics.stability_monotonicity_incorrect < 0
