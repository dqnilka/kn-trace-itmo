"""Tests for Explanation metrics: structure compliance."""

from __future__ import annotations

from pathlib import Path


from evaluation.metrics.explanation import (
    check_structure,
    compute_explanation_metrics,
    load_explanations_from_dir,
    section_coverage,
)


class TestCheckStructure:
    def test_valid_explanation(self):
        text = (
            "**Правильный ответ** — вариант 2.\n\n"
            "**Разбор вариантов**:\n1. ✓ ...\n2. ✗ ...\n\n"
            "**Почему выбранный вариант неверен**: ...\n\n"
            "**Что повторить**: ..."
        )
        assert check_structure(text) is True

    def test_alternative_section_names(self):
        text = (
            "**Что проверял вопрос**: ...\n\n"
            "**Ключевые понятия**: ...\n\n"
            "**Почему ваш ответ неверен**: ...\n\n"
            "**На что обратить внимание**: ..."
        )
        assert check_structure(text) is True

    def test_missing_section_4(self):
        text = (
            "**Правильный ответ** — вариант 2.\n\n"
            "**Разбор вариантов**:\n...\n\n"
            "**Почему выбранный вариант неверен**: ..."
        )
        assert check_structure(text) is False

    def test_missing_section_2(self):
        text = (
            "**Правильный ответ** — вариант 2.\n\n"
            "**Почему выбранный вариант неверен**: ...\n\n"
            "**Что повторить**: ..."
        )
        assert check_structure(text) is False

    def test_empty_text(self):
        assert check_structure("") is False

    def test_only_one_section(self):
        assert check_structure("**Правильный ответ** — 2.") is False


class TestSectionCoverage:
    def test_all_present(self):
        texts = [
            "**Правильный ответ**\n**Разбор вариантов**\n**Почему выбранный вариант неверен**\n**Что повторить**",
        ]
        cov = section_coverage(texts)
        assert all(v == 1.0 for v in cov.values())

    def test_partial(self):
        texts = [
            "**Правильный ответ**\n**Разбор вариантов**",
            "**Правильный ответ**\n**Что повторить**",
        ]
        cov = section_coverage(texts)
        assert cov["section_1_answer"] == 1.0
        assert cov["section_2_analysis"] == 0.5
        assert cov["section_4_review"] == 0.5

    def test_empty(self):
        assert section_coverage([]) == {}


class TestExplanationMetrics:
    def test_on_fixture_data(self, explanation_texts: list[str]):
        metrics = compute_explanation_metrics(explanation_texts)
        assert metrics.n_total == len(explanation_texts)
        assert 0.0 <= metrics.structure_compliance <= 1.0
        assert metrics.n_compliant <= metrics.n_total

    def test_all_good(self):
        good = [
            "**Правильный ответ**\n**Разбор вариантов**\n**Почему выбранный вариант неверен**\n**Что повторить**"
        ] * 5
        metrics = compute_explanation_metrics(good)
        assert metrics.structure_compliance == 1.0
        assert metrics.n_compliant == 5

    def test_all_bad(self):
        bad = ["just some text"] * 5
        metrics = compute_explanation_metrics(bad)
        assert metrics.structure_compliance == 0.0
        assert metrics.n_compliant == 0

    def test_mixed(self):
        good = "**Правильный ответ**\n**Разбор вариантов**\n**Почему выбранный вариант неверен**\n**Что повторить**"
        bad = "just text"
        metrics = compute_explanation_metrics([good, bad, good, bad])
        assert metrics.structure_compliance == 0.5
        assert metrics.n_compliant == 2

    def test_empty_list(self):
        metrics = compute_explanation_metrics([])
        assert metrics.structure_compliance == 0.0
        assert metrics.n_total == 0

    def test_fixture_has_good_and_bad(self, explanation_texts: list[str]):
        metrics = compute_explanation_metrics(explanation_texts)
        assert 0.0 < metrics.structure_compliance < 1.0, (
            f"Expected mix of good and bad, got {metrics.structure_compliance}"
        )


class TestLoadExplanations:
    def test_load_from_dir(self, fixtures_dir: Path):
        texts = load_explanations_from_dir(fixtures_dir / "explanations")
        assert len(texts) >= 10

    def test_load_nonexistent(self, tmp_path: Path):
        texts = load_explanations_from_dir(tmp_path / "nope")
        assert texts == []
