"""Theme Summary quality metrics.

Measures:
  - Format Compliance: correct length, no ## headers, has bold terms
  - Concept Coverage: fraction of theme concepts mentioned in summary
  - Faithfulness (LLM-as-judge, optional)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FAITHFULNESS_PROMPT = """Ты — оценщик качества учебных сводок. Оцени достоверность сводки по теме.

Тема: {theme_name}
Концепты темы: {concepts}

Источники (учебник):
{sources}

Сводка:
{summary}

Разбей сводку на утверждения. Для каждого проверь: подтверждается ли источником?
Ответь JSON: {{"total_claims": N, "supported_claims": M, "faithfulness": M/N}}
"""

HAS_HEADER_PATTERN = re.compile(r"^#{1,3}\s+", re.MULTILINE)
BOLD_PATTERN = re.compile(r"\*\*[^*]+\*\*")
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{2,}")


@dataclass
class SummaryMetrics:
    format_compliance: float
    concept_coverage: float
    n_total: int
    n_format_compliant: int
    avg_word_count: float
    length_details: dict[str, int]
    faithfulness_scores: list[float] | None = None


def check_format(summary: str, min_words: int = 150, max_words: int = 500) -> bool:
    """Check if summary meets format requirements.

    - No ## headers
    - Has at least some bold terms
    - Within word count range
    """
    if HAS_HEADER_PATTERN.search(summary):
        return False
    words = TOKEN_RE.findall(summary)
    if len(words) < min_words or len(words) > max_words:
        return False
    if not BOLD_PATTERN.search(summary):
        return False
    return True


def compute_concept_coverage(summary: str, concept_terms: list[str]) -> float:
    """Fraction of concept terms mentioned in the summary."""
    if not concept_terms:
        return 0.0
    summary_lower = summary.lower()
    mentioned = sum(
        1 for term in concept_terms
        if term.lower() in summary_lower
    )
    return round(mentioned / len(concept_terms), 4)


def compute_summary_metrics(
    summaries: list[str],
    concepts_per_theme: dict[str, list[str]] | None = None,
    theme_names: list[str] | None = None,
) -> SummaryMetrics:
    """Compute all summary quality metrics."""
    if not summaries:
        return SummaryMetrics(
            format_compliance=0.0,
            concept_coverage=0.0,
            n_total=0,
            n_format_compliant=0,
            avg_word_count=0.0,
            length_details={"too_short": 0, "too_long": 0, "ok": 0},
        )

    compliant = sum(1 for s in summaries if check_format(s))
    word_counts = [len(TOKEN_RE.findall(s)) for s in summaries]

    too_short = sum(1 for wc in word_counts if wc < 150)
    too_long = sum(1 for wc in word_counts if wc > 500)
    ok_len = len(summaries) - too_short - too_long

    coverage = 0.0
    if concepts_per_theme and theme_names:
        coverages = []
        for i, (summary, theme_name) in enumerate(
            zip(summaries, theme_names)
        ):
            terms = concepts_per_theme.get(theme_name, [])
            if terms:
                coverages.append(compute_concept_coverage(summary, terms))
        if coverages:
            coverage = round(sum(coverages) / len(coverages), 4)

    return SummaryMetrics(
        format_compliance=round(compliant / len(summaries), 4),
        concept_coverage=coverage,
        n_total=len(summaries),
        n_format_compliant=compliant,
        avg_word_count=round(sum(word_counts) / len(word_counts), 1),
        length_details={"too_short": too_short, "too_long": too_long, "ok": ok_len},
    )


def load_summaries_from_dir(dir_path: Path) -> list[str]:
    """Load all .md files from a directory as summary texts."""
    texts: list[str] = []
    if not dir_path.exists():
        return texts
    for p in sorted(dir_path.glob("*.md")):
        texts.append(p.read_text(encoding="utf-8"))
    return texts


async def compute_faithfulness_llm(
    summaries: list[dict],
    client: object,
    model: str = "gpt-4o-mini",
) -> list[float]:
    """Compute faithfulness scores for summaries using LLM-as-judge.

    Args:
        summaries: list of dicts with keys: theme_name, concepts, sources, summary
        client: OpenAI-compatible client
        model: model name
    """
    import json as json_mod

    scores: list[float] = []
    for item in summaries:
        prompt = FAITHFULNESS_PROMPT.format(**item)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_completion_tokens=200,
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
