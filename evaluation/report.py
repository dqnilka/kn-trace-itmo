"""Markdown report generator with PASS/WARN/FAIL interpretation.

Generates a detailed quality evaluation report from metric results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from evaluation.metrics.bkt import BKTMetrics
from evaluation.metrics.explanation import ExplanationMetrics
from evaluation.metrics.fsrs import FSRSMetrics
from evaluation.metrics.recommender import RecommenderMetrics
from evaluation.metrics.summary import SummaryMetrics


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class MetricResult:
    name: str
    value: float | None
    good_threshold: float | None
    critical_threshold: float | None
    comparison: str
    interpretation: str

    @property
    def status(self) -> Status:
        if self.value is None:
            return Status.SKIP
        if self.comparison == "gte":
            if self.good_threshold is not None and self.value >= self.good_threshold:
                return Status.PASS
            if self.critical_threshold is not None and self.value >= self.critical_threshold:
                return Status.WARN
            return Status.FAIL
        elif self.comparison == "lte":
            if self.good_threshold is not None and self.value <= self.good_threshold:
                return Status.PASS
            if self.critical_threshold is not None and self.value <= self.critical_threshold:
                return Status.WARN
            return Status.FAIL
        elif self.comparison == "gt":
            if self.good_threshold is not None and self.value > self.good_threshold:
                return Status.PASS
            if self.critical_threshold is not None and self.value > self.critical_threshold:
                return Status.WARN
            return Status.FAIL
        elif self.comparison == "lt":
            if self.good_threshold is not None and self.value < self.good_threshold:
                return Status.PASS
            if self.critical_threshold is not None and self.value < self.critical_threshold:
                return Status.WARN
            return Status.FAIL
        return Status.SKIP


def _status_icon(s: Status) -> str:
    return {
        Status.PASS: "✅",
        Status.WARN: "⚠️",
        Status.FAIL: "❌",
        Status.SKIP: "⏭️",
    }.get(s, "❓")


def _val_str(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.4f}"


def build_bkt_results(m: BKTMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Monotonicity (correct)",
            value=m.monotonicity_correct,
            good_threshold=0.001,
            critical_threshold=0.0,
            comparison="gt",
            interpretation="P(L) should increase after correct answers. "
            f"Average ΔP(L) = {m.monotonicity_correct:+.6f}",
        ),
        MetricResult(
            name="Monotonicity (incorrect)",
            value=m.monotonicity_incorrect,
            good_threshold=-0.001,
            critical_threshold=0.0,
            comparison="lt",
            interpretation="P(L) should decrease after incorrect answers. "
            f"Average ΔP(L) = {m.monotonicity_incorrect:+.6f}",
        ),
        MetricResult(
            name="AUC-ROC",
            value=m.auc_roc,
            good_threshold=0.75,
            critical_threshold=0.60,
            comparison="gte",
            interpretation="AUC ≥ 0.75: BKT is informative. "
            "0.60–0.75: weak, parameters not calibrated. "
            "< 0.60: equivalent to random guessing.",
        ),
        MetricResult(
            name="Log-Loss",
            value=m.log_loss_val,
            good_threshold=0.60,
            critical_threshold=0.80,
            comparison="lte",
            interpretation="Log-Loss < 0.60: good calibration. "
            "> 0.80: predictions are overconfident or wrong.",
        ),
        MetricResult(
            name="RMSE",
            value=m.rmse_val,
            good_threshold=0.40,
            critical_threshold=0.60,
            comparison="lte",
            interpretation="Root Mean Square Error of P(correct) vs actual. "
            "< 0.40: good. 0.40–0.60: acceptable. > 0.60: poor predictions.",
        ),
    ]


def build_fsrs_results(m: FSRSMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Stability monotonicity (correct)",
            value=m.stability_monotonicity_correct,
            good_threshold=0.001,
            critical_threshold=0.0,
            comparison="gt",
            interpretation="Memory stability should increase after correct answers. "
            f"Average ΔS = {m.stability_monotonicity_correct:+.2f}s",
        ),
        MetricResult(
            name="Stability monotonicity (incorrect)",
            value=m.stability_monotonicity_incorrect,
            good_threshold=-0.001,
            critical_threshold=0.0,
            comparison="lt",
            interpretation="Memory stability should decrease after incorrect answers. "
            f"Average ΔS = {m.stability_monotonicity_incorrect:+.2f}s",
        ),
        MetricResult(
            name="Calibration ECE",
            value=m.calibration_ece,
            good_threshold=0.05,
            critical_threshold=0.10,
            comparison="lte",
            interpretation="ECE < 0.05: excellent calibration. "
            "0.05–0.10: acceptable. > 0.10: FSRS constants need calibration.",
        ),
    ]


def build_recommender_results(m: RecommenderMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="ECE (calibration)",
            value=m.ece,
            good_threshold=0.05,
            critical_threshold=0.10,
            comparison="lte",
            interpretation="ECE < 0.05: expected_p_correct is well-calibrated. "
            "> 0.10: BKT parameters need fitting.",
        ),
        MetricResult(
            name="Brier Score",
            value=m.brier_score,
            good_threshold=0.25,
            critical_threshold=0.40,
            comparison="lte",
            interpretation="Brier Score < 0.25: good predictions. "
            "> 0.40: predictions are poor.",
        ),
        MetricResult(
            name="Hit Rate@5",
            value=m.hit_rate_at_5,
            good_threshold=0.30,
            critical_threshold=0.10,
            comparison="gte",
            interpretation="Hit Rate ≥ 0.30: recommendations are relevant. "
            "< 0.10: revise scoring weights or loosen filters.",
        ),
        MetricResult(
            name="NDCG@5",
            value=m.ndcg_at_5,
            good_threshold=0.40,
            critical_threshold=0.20,
            comparison="gte",
            interpretation="NDCG ≥ 0.40: good ranking. "
            "< 0.20: ranking is nearly random.",
        ),
        MetricResult(
            name="Topic Coverage",
            value=m.topic_coverage,
            good_threshold=0.60,
            critical_threshold=0.30,
            comparison="gte",
            interpretation="Coverage ≥ 0.60: good diversity. "
            "< 0.30: recommender is stuck on one topic.",
        ),
        MetricResult(
            name="Filter consistency",
            value=1.0 if m.filter_consistency_passed else (0.0 if m.filter_consistency_passed is False else None),
            good_threshold=1.0,
            critical_threshold=0.5,
            comparison="gte",
            interpretation="All recommendations should respect cooldown and mastered filters.",
        ),
    ]


def build_explanation_results(m: ExplanationMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Structure Compliance",
            value=m.structure_compliance,
            good_threshold=0.95,
            critical_threshold=0.90,
            comparison="gte",
            interpretation="≥ 0.95: explanations have all 4 required sections. "
            "< 0.90: prompt needs stricter formatting instructions.",
        ),
        MetricResult(
            name="Faithfulness (LLM-judge)",
            value=float(sum(m.faithfulness_scores) / len(m.faithfulness_scores))
            if m.faithfulness_scores
            else None,
            good_threshold=0.90,
            critical_threshold=0.70,
            comparison="gte",
            interpretation="≥ 0.90: explanations are grounded in context. "
            "< 0.70: LLM is hallucinating facts.",
        ),
        MetricResult(
            name="Answer Relevancy (LLM-judge, 1-5)",
            value=float(sum(m.answer_relevancy_scores) / len(m.answer_relevancy_scores))
            if m.answer_relevancy_scores
            else None,
            good_threshold=4.0,
            critical_threshold=3.0,
            comparison="gte",
            interpretation="≥ 4.0: explanations address the student's error well. "
            "< 3.0: retrieval or prompt issues.",
        ),
    ]


def build_summary_results(m: SummaryMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Format Compliance",
            value=m.format_compliance,
            good_threshold=0.95,
            critical_threshold=0.90,
            comparison="gte",
            interpretation="≥ 0.95: summaries meet format requirements. "
            "< 0.90: prompt needs adjustment.",
        ),
        MetricResult(
            name="Concept Coverage",
            value=m.concept_coverage,
            good_threshold=0.70,
            critical_threshold=0.50,
            comparison="gte",
            interpretation="≥ 0.70: summaries cover most key concepts. "
            "< 0.50: prompt needs to emphasize mentioning all terms.",
        ),
        MetricResult(
            name="Faithfulness (LLM-judge)",
            value=float(sum(m.faithfulness_scores) / len(m.faithfulness_scores))
            if m.faithfulness_scores
            else None,
            good_threshold=0.85,
            critical_threshold=0.70,
            comparison="gte",
            interpretation="≥ 0.85: summaries don't hallucinate. "
            "< 0.70: summaries contain fabricated facts.",
        ),
    ]


def _component_summary(results: list[MetricResult]) -> dict[str, int]:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        counts[r.status.value] += 1
    return counts


def generate_report(
    bkt: BKTMetrics | None = None,
    fsrs: FSRSMetrics | None = None,
    recommender: RecommenderMetrics | None = None,
    explanation: ExplanationMetrics | None = None,
    summary: SummaryMetrics | None = None,
    exam_slug: str = "test-exam",
    mode: str = "autonomous",
    extra_notes: str = "",
) -> str:
    """Generate a complete markdown evaluation report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = []
    sections.append("# Quality Evaluation Report\n")
    sections.append(f"**Date**: {now} | **Exam**: {exam_slug} | **Mode**: {mode}\n")

    all_components: dict[str, list[MetricResult]] = {}
    if bkt:
        all_components["BKT"] = build_bkt_results(bkt)
    if fsrs:
        all_components["FSRS"] = build_fsrs_results(fsrs)
    if recommender:
        all_components["Recommender"] = build_recommender_results(recommender)
    if explanation:
        all_components["Explanation (RAG)"] = build_explanation_results(explanation)
    if summary:
        all_components["Theme Summary"] = build_summary_results(summary)

    summary_rows: list[str] = []
    total_pass = total_warn = total_fail = total_skip = 0
    for comp_name, results in all_components.items():
        counts = _component_summary(results)
        total_pass += counts["PASS"]
        total_warn += counts["WARN"]
        total_fail += counts["FAIL"]
        total_skip += counts["SKIP"]
        summary_rows.append(
            f"| {comp_name} | {len(results)} | {counts['PASS']} | {counts['WARN']} | {counts['FAIL']} | {counts['SKIP']} |"
        )

    sections.append("## Summary\n")
    sections.append("| Component | Metrics | PASS | WARN | FAIL | SKIP |")
    sections.append("|---|---|---|---|---|---|")
    sections.extend(summary_rows)
    sections.append(
        f"| **Total** | **{total_pass + total_warn + total_fail + total_skip}** "
        f"| **{total_pass}** | **{total_warn}** | **{total_fail}** | **{total_skip}** |"
    )
    sections.append("")

    for comp_name, results in all_components.items():
        sections.append(f"## {comp_name}\n")
        sections.append("| Metric | Value | Good Threshold | Critical | Status |")
        sections.append("|---|---|---|---|---|")
        for r in results:
            icon = _status_icon(r.status)
            good_str = _val_str(r.good_threshold) if r.good_threshold is not None else "—"
            crit_str = _val_str(r.critical_threshold) if r.critical_threshold is not None else "—"
            sections.append(
                f"| {r.name} | {_val_str(r.value)} | {good_str} | {crit_str} | {icon} {r.status.value} |"
            )
        sections.append("")
        sections.append("**Interpretation:**\n")
        for r in results:
            sections.append(f"- **{r.name}**: {r.interpretation}")
        sections.append("")

    if total_fail > 0:
        sections.append("## Action Items\n")
        for comp_name, results in all_components.items():
            failed = [r for r in results if r.status == Status.FAIL]
            for r in failed:
                sections.append(f"- **[{comp_name}] {r.name}**: {r.interpretation}")
        sections.append("")

    if extra_notes:
        sections.append(f"## Notes\n\n{extra_notes}\n")

    sections.append("---")
    sections.append("*Report generated by evaluation module — kn-trace-itmo*\n")

    return "\n".join(sections)
