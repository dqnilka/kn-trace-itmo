"""Tests for multiple-choice question detection and prompt selection."""

from __future__ import annotations

from app.rag.generator import (
    COMPOUND_QUESTION_OVERLAY_RU,
    MULTIPLE_CHOICE_OVERLAY_RU,
    SYSTEM_PROMPT_RU,
    detect_multiple_choice,
    extract_correct_answer,
)


SAMPLE_MC = """Вопрос: Найдите неверное утверждение. Права, закрепленные эмиссионной ценной бумагой, переходят к их приобретателю:
Варианты:
1. С переходом права на документарную ценную бумагу переходят все удостоверенные ею права в совокупности
2. Права, удостоверенные предъявительской ценной бумагой, передаются приобретателю только путем вручения
3. Права, удостоверенные ордерной ценной бумагой, передаются приобретателю путем ее вручения
4. Права, удостоверенные именной документарной ценной бумагой, передаются приобретателю путем вручения

Ответ: 2. Права, удостоверенные предъявительской ценной бумагой, передаются приобретателю только путем вручения
"""

SAMPLE_OPEN = """Дайте определение реестра владельцев ценных бумаг и поясните роль регистратора."""

SAMPLE_MC_ROMAN = """Вопрос: Укажите верное утверждение. Информация о владельцах должна быть доступна эмитенту в форме:

I. Реестра владельцев ценных бумаг;
II. Записи о наименовании владельца на бланке сертификата;
III. Записи о наименовании владельца на бланке эмиссионной ценной бумаги.
Варианты:
1. I
2. II
3. I и II
4. I и III

Ответ: 1. I
"""


def test_detect_multiple_choice_with_options_keyword() -> None:
    assert detect_multiple_choice(SAMPLE_MC) is True


def test_detect_multiple_choice_roman_options() -> None:
    assert detect_multiple_choice(SAMPLE_MC_ROMAN) is True


def test_detect_open_question_is_not_mc() -> None:
    assert detect_multiple_choice(SAMPLE_OPEN) is False


def test_extract_correct_answer_present() -> None:
    answer = extract_correct_answer(SAMPLE_MC)
    assert answer is not None
    assert answer.startswith("2.")


def test_extract_correct_answer_absent_in_open() -> None:
    assert extract_correct_answer(SAMPLE_OPEN) is None


def test_overlay_text_contains_key_directives() -> None:
    # Sanity: overlay strings explicitly direct the LLM to handle each option.
    assert "Разбор вариантов" in MULTIPLE_CHOICE_OVERLAY_RU
    assert "ПОЧЕМУ" in MULTIPLE_CHOICE_OVERLAY_RU
    assert "тавтологии" in MULTIPLE_CHOICE_OVERLAY_RU
    assert "подтем" in COMPOUND_QUESTION_OVERLAY_RU
    # Base prompt is unchanged
    assert "Что проверял вопрос" in SYSTEM_PROMPT_RU


def test_detect_empty_or_none() -> None:
    assert detect_multiple_choice("") is False
    assert detect_multiple_choice(None) is False  # type: ignore[arg-type]
