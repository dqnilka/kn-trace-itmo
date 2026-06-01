"""Explanation quality metrics.

Measures:
  - Structure Compliance: does the explanation have all 4 required sections?
  - Faithfulness (LLM-as-judge, optional)
  - Answer Relevancy (LLM-as-judge, optional)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SECTION_PATTERNS = [
    re.compile(r"\*\*Правильный ответ\*\*", re.IGNORECASE),
    re.compile(r"\*\*Что проверял\*\*", re.IGNORECASE),
    re.compile(r"\*\*Что проверял вопрос\*\*", re.IGNORECASE),
]

SECTION_2_PATTERNS = [
    re.compile(r"\*\*Разбор вариантов\*\*", re.IGNORECASE),
    re.compile(r"\*\*Ключевые понятия\*\*", re.IGNORECASE),
    re.compile(r"\*\*Подробное объяснение\*\*", re.IGNORECASE),
]

SECTION_3_PATTERNS = [
    re.compile(r"\*\*Почему выбранный вариант неверен\*\*", re.IGNORECASE),
    re.compile(r"\*\*Почему .*? неверен\*\*", re.IGNORECASE),
    re.compile(r"\*\*Почему ваш ответ неверен\*\*", re.IGNORECASE),
    re.compile(r"\*\*Ошибка\*\*", re.IGNORECASE),
    re.compile(r"\*\*В чём ошибка\*\*", re.IGNORECASE),
    re.compile(r"\*\*Разбор ошибки\*\*", re.IGNORECASE),
]

SECTION_4_PATTERNS = [
    re.compile(r"\*\*Что повторить\*\*", re.IGNORECASE),
    re.compile(r"\*\*На что обратить внимание\*\*", re.IGNORECASE),
]

SECTION_GROUPS = [SECTION_PATTERNS, SECTION_2_PATTERNS, SECTION_3_PATTERNS, SECTION_4_PATTERNS]

FAITHFULNESS_PROMPT = """Ты — оценщик качества объяснений. Оцени достоверность объяснения.

Задача: {question}
Правильный ответ: {correct_answer}
Ответ студента: {picked_answer}

Контекст из учебника:
{context}

Объяснение:
{explanation}

Разбей объяснение на отдельные утверждения. Для каждого утверждения проверь: подтверждается ли оно контекстом из учебника?

Ответь в формате JSON:
{{"total_claims": N, "supported_claims": M, "faithfulness": M/N, "reasoning": "краткое пояснение"}}
Отметь только число supported_claims из total_claims, которые подтверждены контекстом.
"""

RELEVANCY_PROMPT = """Оцени объяснение ошибки студента по 5-балльной шкале.

Вопрос: {question}
Правильный ответ: {correct_answer}
Ответ студента: {picked_answer}
Объяснение: {explanation}

Критерии:
5 — Объясняет правильный ответ И почему вариант студента неверен И даёт советы
4 — Объясняет правильный ответ и почему вариант студента неверен
3 — Объясняет правильный ответ, но не разбирает ошибку студента
2 — Частично релевантно, но упускает суть
1 — Не релевантно вопросу

Ответь только числом от 1 до 5."""


@dataclass
class ExplanationMetrics:
    structure_compliance: float
    n_total: int
    n_compliant: int
    section_coverage: dict[str, float]
    faithfulness_scores: list[float] | None = None
    answer_relevancy_scores: list[float] | None = None


def check_structure(explanation_md: str) -> bool:
    """Check if explanation has all 4 required sections."""
    for patterns in SECTION_GROUPS:
        if not any(p.search(explanation_md) for p in patterns):
            return False
    return True


def section_coverage(explanations: list[str]) -> dict[str, float]:
    """Compute per-section presence rate."""
    n = len(explanations)
    if n == 0:
        return {}
    coverage: dict[str, float] = {}
    names = ["section_1_answer", "section_2_analysis", "section_3_why_wrong", "section_4_review"]
    for name, patterns in zip(names, SECTION_GROUPS):
        count = sum(1 for e in explanations if any(p.search(e) for p in patterns))
        coverage[name] = round(count / n, 4)
    return coverage


def compute_explanation_metrics(
    explanations: list[str],
) -> ExplanationMetrics:
    """Compute structure compliance metrics for explanations."""
    if not explanations:
        return ExplanationMetrics(
            structure_compliance=0.0,
            n_total=0,
            n_compliant=0,
            section_coverage={},
        )

    compliant = sum(1 for e in explanations if check_structure(e))
    return ExplanationMetrics(
        structure_compliance=round(compliant / len(explanations), 4),
        n_total=len(explanations),
        n_compliant=compliant,
        section_coverage=section_coverage(explanations),
    )


def load_explanations_from_dir(dir_path: Path) -> list[str]:
    """Load all .md files from a directory as explanation texts."""
    texts: list[str] = []
    if not dir_path.exists():
        return texts
    for p in sorted(dir_path.glob("*.md")):
        texts.append(p.read_text(encoding="utf-8"))
    return texts


async def compute_faithfulness_llm(
    explanations: list[dict],
    client: object,
    model: str = "gpt-4o-mini",
) -> list[float]:
    """Compute faithfulness scores using LLM-as-judge.

    Args:
        explanations: list of dicts with keys:
            question, correct_answer, picked_answer, context, explanation
        client: OpenAI-compatible client
        model: model name
    """
    import json as json_mod

    scores: list[float] = []
    for item in explanations:
        prompt = FAITHFULNESS_PROMPT.format(**item)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_completion_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = json_mod.loads(raw)
            total = max(parsed.get("total_claims", 1), 1)
            supported = parsed.get("supported_claims", 0)
            scores.append(supported / total)
        except Exception:
            scores.append(0.0)
    return scores


async def compute_answer_relevancy_llm(
    explanations: list[dict],
    client: object,
    model: str = "gpt-4o-mini",
) -> list[float]:
    """Compute answer relevancy scores (1-5) using LLM-as-judge.

    Args:
        explanations: list of dicts with keys:
            question, correct_answer, picked_answer, explanation
        client: OpenAI-compatible client
        model: model name
    """
    scores: list[float] = []
    for item in explanations:
        prompt = RELEVANCY_PROMPT.format(**item)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_completion_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            score = float(re.search(r"[1-5]", raw).group())
            scores.append(score)
        except Exception:
            scores.append(1.0)
    return scores
