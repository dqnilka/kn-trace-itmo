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
            name="Монотонность (верные)",
            value=m.monotonicity_correct,
            good_threshold=0.001,
            critical_threshold=0.0,
            comparison="gt",
            interpretation="P(L) должен расти после правильных ответов. "
            f"Среднее ΔP(L) = {m.monotonicity_correct:+.6f}",
        ),
        MetricResult(
            name="Монотонность (неверные)",
            value=m.monotonicity_incorrect,
            good_threshold=-0.001,
            critical_threshold=0.0,
            comparison="lt",
            interpretation="P(L) должен падать после ошибок. "
            f"Среднее ΔP(L) = {m.monotonicity_incorrect:+.6f}",
        ),
        MetricResult(
            name="AUC-ROC",
            value=m.auc_roc,
            good_threshold=0.75,
            critical_threshold=0.60,
            comparison="gte",
            interpretation="AUC ≥ 0.75: BKT информативен. "
            "0.60–0.75: слабый, параметры не калиброваны. "
            "< 0.60: эквивалент случайному угадыванию.",
        ),
        MetricResult(
            name="Log-Loss",
            value=m.log_loss_val,
            good_threshold=0.60,
            critical_threshold=0.80,
            comparison="lte",
            interpretation="Log-Loss < 0.60: хорошая калибровка. "
            "> 0.80: прогнозы излишне уверены или ошибочны.",
        ),
        MetricResult(
            name="RMSE",
            value=m.rmse_val,
            good_threshold=0.40,
            critical_threshold=0.60,
            comparison="lte",
            interpretation="Ср.-кв. ошибка P(correct) vs факт. "
            "< 0.40: хорошо. 0.40–0.60: приемлемо. > 0.60: плохие прогнозы.",
        ),
    ]


def build_fsrs_results(m: FSRSMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Монотонность стабильности (верные)",
            value=m.stability_monotonicity_correct,
            good_threshold=0.001,
            critical_threshold=0.0,
            comparison="gt",
            interpretation="Стабильность памяти должна расти после правильных ответов. "
            f"Среднее ΔS = {m.stability_monotonicity_correct:+.2f}s",
        ),
        MetricResult(
            name="Монотонность стабильности (неверные)",
            value=m.stability_monotonicity_incorrect,
            good_threshold=-0.001,
            critical_threshold=0.0,
            comparison="lt",
            interpretation="Стабильность памяти должна падать после ошибок. "
            f"Среднее ΔS = {m.stability_monotonicity_incorrect:+.2f}s",
        ),
        MetricResult(
            name="Калибровка ECE",
            value=m.calibration_ece,
            good_threshold=0.05,
            critical_threshold=0.10,
            comparison="lte",
            interpretation="ECE < 0.05: отличная калибровка. "
            "0.05–0.10: приемлемо. > 0.10: константы FSRS требуют калибровки.",
        ),
    ]


def build_recommender_results(m: RecommenderMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Калибровка ECE",
            value=m.ece,
            good_threshold=0.05,
            critical_threshold=0.10,
            comparison="lte",
            interpretation="ECE < 0.05: expected_p_correct хорошо калиброван. "
            "> 0.10: параметры BKT требуют подгонки.",
        ),
        MetricResult(
            name="Brier Score",
            value=m.brier_score,
            good_threshold=0.25,
            critical_threshold=0.40,
            comparison="lte",
            interpretation="Brier Score < 0.25: хорошие прогнозы. "
            "> 0.40: прогнозы слабые.",
        ),
        MetricResult(
            name="Hit Rate@5",
            value=m.hit_rate_at_5,
            good_threshold=0.30,
            critical_threshold=0.10,
            comparison="gte",
            interpretation="Hit Rate ≥ 0.30: рекомендации релевантны. "
            "< 0.10: пересмотрите веса или ослабьте фильтры.",
        ),
        MetricResult(
            name="NDCG@5",
            value=m.ndcg_at_5,
            good_threshold=0.40,
            critical_threshold=0.20,
            comparison="gte",
            interpretation="NDCG ≥ 0.40: хороший ранг. "
            "< 0.20: ранжирование почти случайное.",
        ),
        MetricResult(
            name="Охват тем",
            value=m.topic_coverage,
            good_threshold=0.60,
            critical_threshold=0.30,
            comparison="gte",
            interpretation="Coverage ≥ 0.60: хорошее разнообразие. "
            "< 0.30: рекомендер застрял на одной теме.",
        ),
        MetricResult(
            name="Согласованность фильтров",
            value=1.0 if m.filter_consistency_passed else (0.0 if m.filter_consistency_passed is False else None),
            good_threshold=1.0,
            critical_threshold=0.5,
            comparison="gte",
            interpretation="Все рекомендации должны учитывать cooldown и фильтры усвоенных.",
        ),
    ]


def build_explanation_results(m: ExplanationMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Соответствие структуре",
            value=m.structure_compliance,
            good_threshold=0.95,
            critical_threshold=0.90,
            comparison="gte",
            interpretation="≥ 0.95: объяснения содержат все 4 обязательных раздела. "
            "< 0.90: промпт требует более строгих инструкций по форматированию.",
        ),
        MetricResult(
            name="Достоверность (LLM-судья)",
            value=float(sum(m.faithfulness_scores) / len(m.faithfulness_scores))
            if m.faithfulness_scores
            else None,
            good_threshold=0.90,
            critical_threshold=0.70,
            comparison="gte",
            interpretation="≥ 0.90: объяснения основаны на контексте. "
            "< 0.70: LLM галлюцинирует факты.",
        ),
        MetricResult(
            name="Релевантность ответа (LLM-судья, 1-5)",
            value=float(sum(m.answer_relevancy_scores) / len(m.answer_relevancy_scores))
            if m.answer_relevancy_scores
            else None,
            good_threshold=4.0,
            critical_threshold=3.0,
            comparison="gte",
            interpretation="≥ 4.0: объяснения хорошо описывают ошибку студента. "
            "< 3.0: проблемы с поиском или промптом.",
        ),
    ]


def build_summary_results(m: SummaryMetrics) -> list[MetricResult]:
    return [
        MetricResult(
            name="Соответствие формату",
            value=m.format_compliance,
            good_threshold=0.95,
            critical_threshold=0.90,
            comparison="gte",
            interpretation="≥ 0.95: саммари соответствуют формату. "
            "< 0.90: промпт требует корректировки.",
        ),
        MetricResult(
            name="Охват концепций",
            value=m.concept_coverage,
            good_threshold=0.70,
            critical_threshold=0.50,
            comparison="gte",
            interpretation="≥ 0.70: саммари покрывают большинство ключевых концепций. "
            "< 0.50: промпт должен emphasировать упоминание всех терминов.",
        ),
        MetricResult(
            name="Достоверность (LLM-судья)",
            value=float(sum(m.faithfulness_scores) / len(m.faithfulness_scores))
            if m.faithfulness_scores
            else None,
            good_threshold=0.85,
            critical_threshold=0.70,
            comparison="gte",
            interpretation="≥ 0.85: саммари без галлюцинаций. "
            "< 0.70: саммари содержат выдуманные факты.",
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
    sections.append("# Отчёт оценки качества\n")
    sections.append(f"**Дата**: {now} | **Экзамен**: {exam_slug} | **Режим**: {mode}\n")

    all_components: dict[str, list[MetricResult]] = {}
    if bkt:
        all_components["BKT"] = build_bkt_results(bkt)
    if fsrs:
        all_components["FSRS"] = build_fsrs_results(fsrs)
    if recommender:
        all_components["Рекомендатель"] = build_recommender_results(recommender)
    if explanation:
        all_components["Объяснение (RAG)"] = build_explanation_results(explanation)
    if summary:
        all_components["Сводка по темам"] = build_summary_results(summary)

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

    sections.append("## Сводка\n")
    sections.append("| Компонент | Метрик | ПАСС | ПРЕД | ПРОВАЛ | ПРОП |")
    sections.append("|---|---|---|---|---|---|")
    sections.extend(summary_rows)
    sections.append(
        f"| **Total** | **{total_pass + total_warn + total_fail + total_skip}** "
        f"| **{total_pass}** | **{total_warn}** | **{total_fail}** | **{total_skip}** |"
    )
    sections.append("")

    for comp_name, results in all_components.items():
        sections.append(f"## {comp_name}\n")
        sections.append("| Метрика | Значение | Порог (хор.) | Критич. | Статус |")
        sections.append("|---|---|---|---|---|")
        for r in results:
            icon = _status_icon(r.status)
            good_str = _val_str(r.good_threshold) if r.good_threshold is not None else "—"
            crit_str = _val_str(r.critical_threshold) if r.critical_threshold is not None else "—"
            sections.append(
                f"| {r.name} | {_val_str(r.value)} | {good_str} | {crit_str} | {icon} {r.status.value} |"
            )
        sections.append("")
        sections.append("**Интерпретация:**\n")
        for r in results:
            sections.append(f"- **{r.name}**: {r.interpretation}")
        sections.append("")

    if total_fail > 0:
        sections.append("## Действия\n")
        for comp_name, results in all_components.items():
            failed = [r for r in results if r.status == Status.FAIL]
            for r in failed:
                sections.append(f"- **[{comp_name}] {r.name}**: {r.interpretation}")
        sections.append("")

    if extra_notes:
        sections.append(f"## Заметки\n\n{extra_notes}\n")

    sections.append("---")
    sections.append("*Отчёт создан модулем оценки — kn-trace-itmo*\n")

    return "\n".join(sections)
