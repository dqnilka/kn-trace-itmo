"""Tests for Summary metrics: format compliance, concept coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.metrics.summary import (
    check_format,
    compute_concept_coverage,
    compute_summary_metrics,
    load_summaries_from_dir,
)


class TestCheckFormat:
    def test_valid_summary(self):
        text = (
            "Финансовый рынок — это совокупность отношений по поводу распределения средств. "
            "**Финансовый рынок** выполняет важную функцию перераспределения капитала. "
            "**Ценная бумага** — документ, удостоверяющий права. "
            "Обратите внимание на различия между биржевым и внебиржевым рынками. "
            "Помните, что диверсификация снижает риск портфеля."
        )
        padded = text + " " + " ".join(["слово"] * 150)
        assert check_format(padded) is True

    def test_too_short(self):
        text = "**Короткий текст** без достаточного количества слов."
        assert check_format(text, min_words=150) is False

    def test_too_long(self):
        text = "**Текст** " + "слово " * 600
        assert check_format(text, max_words=500) is False

    def test_has_headers(self):
        text = "## Заголовок\n\n" + "**Текст** " + "слово " * 200
        assert check_format(text) is False

    def test_no_bold(self):
        text = "Просто текст без выделений. " * 50
        assert check_format(text, min_words=50) is False

    def test_empty(self):
        assert check_format("") is False


class TestConceptCoverage:
    def test_full_coverage(self):
        summary = "Финансовый рынок и ценная бумага — ключевые понятия."
        terms = ["Финансовый рынок", "ценная бумага"]
        assert compute_concept_coverage(summary, terms) == 1.0

    def test_partial_coverage(self):
        summary = "Финансовый рынок — важное понятие."
        terms = ["Финансовый рынок", "ценная бумага", "акция"]
        assert compute_concept_coverage(summary, terms) == pytest.approx(1 / 3, abs=0.01)

    def test_no_coverage(self):
        summary = "Ничего релевантного."
        terms = ["Финансовый рынок", "ценная бумага"]
        assert compute_concept_coverage(summary, terms) == 0.0

    def test_empty_terms(self):
        assert compute_concept_coverage("текст", []) == 0.0

    def test_case_insensitive(self):
        summary = "ФИНАНСОВЫЙ РЫНОК — это..."
        assert compute_concept_coverage(summary, ["финансовый рынок"]) == 1.0


class TestSummaryMetrics:
    def test_on_fixture_data(self, summary_texts: list[str]):
        metrics = compute_summary_metrics(summary_texts)
        assert metrics.n_total == len(summary_texts)
        assert 0.0 <= metrics.format_compliance <= 1.0

    def test_all_good(self):
        good = "**Текст** " + "слово " * 200
        metrics = compute_summary_metrics([good, good, good])
        assert metrics.format_compliance == 1.0

    def test_all_bad(self):
        bad = "коротко"
        metrics = compute_summary_metrics([bad, bad])
        assert metrics.format_compliance == 0.0

    def test_length_details(self, summary_texts: list[str]):
        metrics = compute_summary_metrics(summary_texts)
        assert metrics.length_details["too_short"] + metrics.length_details["too_long"] + metrics.length_details["ok"] == metrics.n_total

    def test_with_concepts(self, summary_texts: list[str]):
        concepts_per_theme = {
            "1.1": ["Финансовый рынок", "перераспределение"],
            "1.2": ["Ценная бумага", "облигация"],
        }
        theme_names = ["1.1", "1.2"]
        if len(summary_texts) >= 2:
            metrics = compute_summary_metrics(
                summary_texts[:2],
                concepts_per_theme=concepts_per_theme,
                theme_names=theme_names,
            )
            assert metrics.concept_coverage >= 0.0

    def test_empty(self):
        metrics = compute_summary_metrics([])
        assert metrics.format_compliance == 0.0
        assert metrics.n_total == 0

    def test_fixture_has_mix(self, summary_texts: list[str]):
        metrics = compute_summary_metrics(summary_texts)
        assert 0.0 < metrics.format_compliance < 1.0, (
            f"Expected mix of good and bad summaries, got {metrics.format_compliance}"
        )


class TestLoadSummaries:
    def test_load_from_dir(self, fixtures_dir: Path):
        texts = load_summaries_from_dir(fixtures_dir / "summaries")
        assert len(texts) >= 10

    def test_load_nonexistent(self, tmp_path: Path):
        texts = load_summaries_from_dir(tmp_path / "nope")
        assert texts == []
