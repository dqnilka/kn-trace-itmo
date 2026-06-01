"""Tests for Recommender metrics: ECE, Brier, Hit@5, NDCG@5, coverage, filters."""

from __future__ import annotations


from evaluation.metrics.recommender import (
    brier_score,
    check_filter_consistency,
    compute_calibration_from_events,
    compute_recommender_metrics,
    hit_rate_at_k,
    ndcg_at_k,
    topic_coverage,
)


class TestCalibration:
    def test_ece_from_events(self, events: list[dict]):
        predictions = [0.5] * len(events)
        ece, bs = compute_calibration_from_events(events, predictions)
        assert ece is not None
        assert bs is not None
        assert 0.0 <= ece <= 1.0
        assert 0.0 <= bs <= 1.0

    def test_perfect_predictions(self):
        events = [
            {"is_correct": True},
            {"is_correct": True},
            {"is_correct": True},
            {"is_correct": True},
            {"is_correct": False},
            {"is_correct": False},
            {"is_correct": False},
            {"is_correct": False},
        ]
        predictions = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]
        ece, bs = compute_calibration_from_events(events, predictions)
        assert ece is not None
        assert ece < 0.3
        assert bs is not None
        assert bs < 0.05

    def test_too_few_events(self):
        events = [{"is_correct": True}]
        ece, bs = compute_calibration_from_events(events, [0.5])
        assert ece is None
        assert bs is None


class TestBrierScore:
    def test_perfect_score(self):
        bs = brier_score([1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0])
        assert bs == 0.0

    def test_worst_score(self):
        bs = brier_score([0.0, 0.0], [1.0, 1.0])
        assert bs == 1.0

    def test_empty(self):
        assert brier_score([], []) == 0.0


class TestHitRate:
    def test_perfect_hit(self):
        recs = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        actuals = [3, 8]
        hr = hit_rate_at_k(recs, actuals, k=5)
        assert hr == 1.0

    def test_no_hit(self):
        recs = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        actuals = [99, 100]
        hr = hit_rate_at_k(recs, actuals, k=5)
        assert hr == 0.0

    def test_partial_hit(self):
        recs = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        actuals = [3, 99]
        hr = hit_rate_at_k(recs, actuals, k=5)
        assert hr == 0.5

    def test_empty(self):
        assert hit_rate_at_k([], [], k=5) == 0.0


class TestNDCG:
    def test_perfect_ranking(self):
        recs = [[1, 2, 3, 4, 5]]
        relevant = [[1, 2, 3]]
        ndcg = ndcg_at_k(recs, relevant, k=5)
        assert ndcg == 1.0

    def test_worst_ranking(self):
        recs = [[99, 100, 101, 102, 103]]
        relevant = [[1, 2, 3]]
        ndcg = ndcg_at_k(recs, relevant, k=5)
        assert ndcg == 0.0

    def test_partial_ranking(self):
        recs = [[1, 99, 2, 98, 3]]
        relevant = [[1, 2, 3]]
        ndcg = ndcg_at_k(recs, relevant, k=5)
        assert 0.0 < ndcg <= 1.0

    def test_empty(self):
        assert ndcg_at_k([], [], k=5) == 0.0


class TestTopicCoverage:
    def test_full_coverage(self):
        tasks = [
            {"theme_code": "1.1"}, {"theme_code": "1.2"},
            {"theme_code": "1.3"}, {"theme_code": "2.1"}, {"theme_code": "2.2"},
        ]
        themes = ["1.1", "1.2", "1.3", "2.1", "2.2"]
        assert topic_coverage(tasks, themes) == 1.0

    def test_partial_coverage(self):
        tasks = [{"theme_code": "1.1"}, {"theme_code": "1.2"}]
        themes = ["1.1", "1.2", "1.3", "2.1", "2.2"]
        cov = topic_coverage(tasks, themes)
        assert cov == 0.4

    def test_no_coverage(self):
        tasks = [{"theme_code": "9.9"}]
        themes = ["1.1", "1.2", "1.3"]
        assert topic_coverage(tasks, themes) == 0.0

    def test_empty_themes(self):
        assert topic_coverage([{"theme_code": "1.1"}], []) == 0.0


class TestFilterConsistency:
    def test_no_violation(self):
        recs = [{"task_id": 10}, {"task_id": 11}, {"task_id": 12}]
        cooldown = [1, 2, 3]
        assert check_filter_consistency(recs, cooldown, []) is True

    def test_cooldown_violation(self):
        recs = [{"task_id": 5}, {"task_id": 1}, {"task_id": 3}]
        cooldown = [1, 2, 3]
        assert check_filter_consistency(recs, cooldown, []) is False

    def test_empty_recommendations(self):
        assert check_filter_consistency([], [], []) is True


class TestRecommenderMetricsIntegration:
    def test_compute_with_events_only(self, events: list[dict], theme_codes: list[str]):
        metrics = compute_recommender_metrics(
            events=events,
            graph_themes=theme_codes,
        )
        assert metrics.n_events == len(events)
        assert metrics.topic_coverage is None

    def test_compute_with_predictions(self, events: list[dict]):
        predictions = [0.5] * len(events)
        metrics = compute_recommender_metrics(
            events=events,
            predictions=predictions,
        )
        assert metrics.ece is not None
        assert metrics.brier_score is not None

    def test_mismatched_predictions(self, events: list[dict]):
        metrics = compute_recommender_metrics(
            events=events,
            predictions=[0.5],
        )
        assert metrics.ece is None
