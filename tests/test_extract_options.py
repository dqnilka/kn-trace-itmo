"""Tests for multiple-choice option extraction."""

from __future__ import annotations

from app.rag.generator import extract_options


SAMPLE_MC_NUMERIC = """Вопрос: Найдите неверное утверждение.
Варианты:
1. С переходом права на документарную ценную бумагу переходят все удостоверенные ею права в совокупности
2. Права, удостоверенные предъявительской ценной бумагой, передаются приобретателю только путем вручения
3. Права, удостоверенные ордерной ценной бумагой, передаются с совершением индоссамента
4. Права, удостоверенные именной документарной ценной бумагой, передаются в форме цессии

Ответ: 2. Права, удостоверенные предъявительской ценной бумагой, передаются приобретателю только путем вручения
"""

SAMPLE_MC_ROMAN = """Вопрос: Информация должна быть доступна в форме:

I. Реестра владельцев ценных бумаг;
II. Записи на бланке сертификата;
III. Записи на бланке эмиссионной ценной бумаги.

Ответ: 1. I
"""


def test_extract_numeric_options() -> None:
    opts = extract_options(SAMPLE_MC_NUMERIC)
    assert len(opts) == 4, f"Expected 4 options, got {len(opts)}: {opts}"
    assert "переходят все удостоверенные" in opts[0]
    assert "вручения" in opts[1]
    assert "индоссамента" in opts[2]
    assert "цессии" in opts[3]


def test_extract_options_does_not_include_answer_text() -> None:
    """The 'Ответ: 2. ...' line must NOT add a 5th option."""
    opts = extract_options(SAMPLE_MC_NUMERIC)
    # The answer line text starts with "Права, удостоверенные предъявительской" — same prefix
    # as option 2; we make sure we don't double-count it.
    assert len(opts) == 4
    # There should be no duplicate option containing "только путем вручения" twice
    matches = [o for o in opts if "только путем вручения" in o]
    assert len(matches) == 1


def test_extract_roman_options() -> None:
    opts = extract_options(SAMPLE_MC_ROMAN)
    assert len(opts) >= 3
    assert any("Реестра" in o for o in opts)
    assert any("сертификата" in o for o in opts)


def test_extract_options_empty() -> None:
    assert extract_options("") == []
    assert extract_options("Дайте определение реестра.") == []
