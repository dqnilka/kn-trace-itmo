"""Integration tests for evaluation runner and report generator."""

from __future__ import annotations

from pathlib import Path


from evaluation.metrics.bkt import BKTMetrics
from evaluation.report import MetricResult, Status, generate_report
from evaluation.runner import run_autonomous


class TestRunnerAutonomous:
    def test_run_produces_all_metrics(self, fixtures_dir: Path):
        bkt, fsrs, rec, explanation, summary, mode = run_autonomous(fixtures_dir)
        assert bkt is not None, "BKT metrics should be computed"
        assert fsrs is not None, "FSRS metrics should be computed"
        assert rec is not None, "Recommender metrics should be computed"
        assert explanation is not None, "Explanation metrics should be computed"
        assert summary is not None, "Summary metrics should be computed"
        assert "autonomous" in mode

    def test_run_bkt_has_values(self, fixtures_dir: Path):
        bkt, _, _, _, _, _ = run_autonomous(fixtures_dir)
        assert bkt.n_events > 0
        assert bkt.n_concepts_seen > 0
        assert bkt.auc_roc is not None

    def test_run_fsrs_has_values(self, fixtures_dir: Path):
        _, fsrs, _, _, _, _ = run_autonomous(fixtures_dir)
        assert fsrs.n_events > 0
        assert fsrs.stability_monotonicity_correct > 0

    def test_run_explanation_has_values(self, fixtures_dir: Path):
        _, _, _, explanation, _, _ = run_autonomous(fixtures_dir)
        assert explanation.n_total > 0
        assert 0.0 <= explanation.structure_compliance <= 1.0

    def test_run_summary_has_values(self, fixtures_dir: Path):
        _, _, _, _, summary, _ = run_autonomous(fixtures_dir)
        assert summary.n_total > 0
        assert 0.0 <= summary.format_compliance <= 1.0


class TestReportGenerator:
    def test_generate_full_report(self, fixtures_dir: Path):
        bkt, fsrs, rec, explanation, summary, mode = run_autonomous(fixtures_dir)
        report = generate_report(
            bkt=bkt, fsrs=fsrs, recommender=rec,
            explanation=explanation, summary=summary,
            exam_slug="test-exam", mode=mode,
        )
        assert "# Отчёт оценки качества" in report
        assert "## Сводка" in report
        assert "## BKT" in report
        assert "## FSRS" in report
        assert "## Рекомендатель" in report
        assert "## Объяснение" in report
        assert "## Сводка по темам" in report
        assert "PASS" in report or "WARN" in report or "FAIL" in report

    def test_report_with_only_bkt(self):
        bkt = BKTMetrics(
            monotonicity_correct=0.08,
            monotonicity_incorrect=-0.05,
            auc_roc=0.78,
            log_loss_val=0.55,
            rmse_val=0.42,
            n_events=100,
            n_concepts_seen=10,
        )
        report = generate_report(bkt=bkt, exam_slug="test")
        assert "## BKT" in report
        assert "AUC-ROC" in report
        assert "0.7800" in report

    def test_report_with_none_values(self):
        report = generate_report(
            bkt=BKTMetrics(
                monotonicity_correct=0.05,
                monotonicity_incorrect=-0.03,
                auc_roc=None,
                log_loss_val=None,
                rmse_val=None,
                n_events=5,
                n_concepts_seen=2,
            ),
            exam_slug="test",
        )
        assert "—" in report

    def test_report_empty(self):
        report = generate_report(exam_slug="empty")
        assert "# Отчёт оценки качества" in report
        assert "## Сводка" in report

    def test_report_has_status_icons(self, fixtures_dir: Path):
        bkt, fsrs, rec, explanation, summary, mode = run_autonomous(fixtures_dir)
        report = generate_report(
            bkt=bkt, fsrs=fsrs, recommender=rec,
            explanation=explanation, summary=summary,
            exam_slug="test-exam", mode=mode,
        )
        has_icon = any(icon in report for icon in ["✅", "⚠️", "❌", "⏭️"])
        assert has_icon, "Report should contain status icons"

    def test_report_saved_to_file(self, fixtures_dir: Path, tmp_path: Path):
        bkt, fsrs, rec, explanation, summary, mode = run_autonomous(fixtures_dir)
        report = generate_report(
            bkt=bkt, fsrs=fsrs, recommender=rec,
            explanation=explanation, summary=summary,
            exam_slug="test-exam", mode=mode,
        )
        out = tmp_path / "report.md"
        out.write_text(report, encoding="utf-8")
        assert out.exists()
        assert out.stat().st_size > 100


class TestMetricResult:
    def test_pass_gte(self):
        r = MetricResult("test", 0.85, 0.75, 0.60, "gte", "")
        assert r.status == Status.PASS

    def test_warn_gte(self):
        r = MetricResult("test", 0.65, 0.75, 0.60, "gte", "")
        assert r.status == Status.WARN

    def test_fail_gte(self):
        r = MetricResult("test", 0.50, 0.75, 0.60, "gte", "")
        assert r.status == Status.FAIL

    def test_skip_none(self):
        r = MetricResult("test", None, 0.75, 0.60, "gte", "")
        assert r.status == Status.SKIP

    def test_pass_lte(self):
        r = MetricResult("test", 0.03, 0.05, 0.10, "lte", "")
        assert r.status == Status.PASS

    def test_warn_lte(self):
        r = MetricResult("test", 0.07, 0.05, 0.10, "lte", "")
        assert r.status == Status.WARN

    def test_fail_lte(self):
        r = MetricResult("test", 0.15, 0.05, 0.10, "lte", "")
        assert r.status == Status.FAIL

    def test_pass_gt(self):
        r = MetricResult("test", 0.01, 0.0, None, "gt", "")
        assert r.status == Status.PASS

    def test_fail_gt(self):
        r = MetricResult("test", 0.0, 0.0, None, "gt", "")
        assert r.status == Status.FAIL
