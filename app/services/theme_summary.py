"""LLM-generated, product-grade theory article per exam theme.

Raw MD sections from the textbook are messy:
  * page markers like ``{378}--------``
  * cross-references to unrelated chapters
  * footnotes / running headers
  * 1000+ char paragraphs that overflow the learn-card

This module asks GPT to rewrite the top-K sections into a focused 200-300 word
explainer **strictly from the provided context** — same RAG-no-fabricate
guarantee as ``bank_explain``. Results cache to disk per theme; one LLM call
per theme on first request, instant afterwards.

Cache layout::

    data/exams/<slug>/theme_summaries/<theme_code>.md
    data/exams/<slug>/theme_summaries/<theme_code>.meta.json   (timestamp, source hashes)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.exams.registry import Exam

logger = get_logger(__name__)


SYSTEM_PROMPT = """Ты — методист курса подготовки к экзамену. На вход получаешь: название темы; перечень ПОНЯТИЙ, которые реально проверяются заданиями этой темы (с определениями); несколько примеров самих ЗАДАНИЙ темы (с верным ответом); сырые секции учебника. Твоя задача — собрать короткое объяснение (200–300 слов), которое готовит студента ИМЕННО к этим заданиям.

ТРЕБОВАНИЯ:
- Объясняй то, что проверяется в перечисленных понятиях и заданиях. Не уходи в смежные темы, которых в заданиях нет.
- Используй ТОЛЬКО факты из предоставленных определений и секций. Не выдумывай цифры, законы, определения.
- Не цитируй формулировки заданий и варианты ответов дословно — раскрывай стоящие за ними понятия, чтобы студент решал подобные задания сам.
- Очисти текст от артефактов учебника: номера страниц ({NNN}---), номера разделов (16.5...), переносы вида «РАЗДЕЛ ТРЕТИ Й», ссылки «см. раздел X».
- Не повторяй название темы в начале — оно уже видно над текстом.
- Структура (строгий markdown, без заголовков # и ##):
  1. 1 абзац — суть темы и главное определение.
  2. Ключевые понятия — **bold-термин** + 1-2 предложения определения. Бери понятия из списка проверяемых. 2-5 пунктов.
  3. На что обратить внимание на экзамене — 2-3 тезисные подсказки/типичные ловушки, исходя из того, что спрашивают задания.
- Пиши на русском, нейтральный учебный тон, без воды и без «как мы видим из контекста».
- Если материала мало — честно напиши «Материала в учебнике немного» и тезисно перечисли, что есть, не приукрашивая."""


@dataclass
class ThemeSummary:
    summary_md: str
    cached: bool
    generated_at: float


def _cache_paths(exam: Exam, theme_code: str) -> tuple[Path, Path]:
    base = exam.root / "theme_summaries"
    return base / f"{theme_code}.md", base / f"{theme_code}.meta.json"


def _content_hash(
    theme_name: str,
    sections: list[dict],
    tasks: list[dict] | None = None,
    concepts: list[dict] | None = None,
) -> str:
    h = hashlib.sha256()
    # Prompt-version tag: bump when the grounding strategy changes so stale
    # task-agnostic summaries are regenerated rather than served from cache.
    h.update(b"v2-task-grounded\n")
    h.update(theme_name.encode("utf-8"))
    for s in sections:
        h.update((s.get("section_path", "") + "\n" + s.get("excerpt", "")).encode("utf-8"))
    for c in concepts or []:
        h.update((str(c.get("term", "")) + "\n" + str(c.get("definition", ""))).encode("utf-8"))
    for t in tasks or []:
        h.update((str(t.get("task_text", "")) + "\n" + str(t.get("correct", ""))).encode("utf-8"))
    return h.hexdigest()[:16]


def get_cached(exam: Exam, theme_code: str, hash_: str) -> ThemeSummary | None:
    md_path, meta_path = _cache_paths(exam, theme_code)
    if not md_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("content_hash") != hash_:
            return None  # source changed — regenerate
        return ThemeSummary(
            summary_md=md_path.read_text(encoding="utf-8"),
            cached=True,
            generated_at=float(meta.get("generated_at", 0)),
        )
    except Exception:  # noqa: BLE001
        return None


def save_cache(
    exam: Exam,
    theme_code: str,
    summary_md: str,
    hash_: str,
) -> None:
    md_path, meta_path = _cache_paths(exam, theme_code)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(summary_md, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {"content_hash": hash_, "generated_at": time.time()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _user_prompt(
    chapter_name: str | None,
    theme_name: str,
    sections: list[dict],
    tasks: list[dict] | None = None,
    concepts: list[dict] | None = None,
) -> str:
    parts = [f"Тема: {theme_name}"]
    if chapter_name:
        parts.append(f"Глава: {chapter_name}")

    if concepts:
        parts.append("\nПонятия, проверяемые заданиями темы (с определениями):\n")
        for c in concepts:
            term = str(c.get("term") or "").strip()
            definition = str(c.get("definition") or "").strip()[:600]
            if term:
                parts.append(f"- **{term}** — {definition}" if definition else f"- **{term}**")

    if tasks:
        parts.append("\nПримеры заданий темы (что реально спрашивают на экзамене):\n")
        for i, t in enumerate(tasks, start=1):
            q = str(t.get("task_text") or "").strip()[:500]
            correct = str(t.get("correct") or "").strip()[:300]
            block = f"[Задание {i}] {q}"
            if correct:
                block += f"\nВерный ответ: {correct}"
            parts.append(block)

    if sections:
        parts.append("\nСекции учебника:\n")
        for i, s in enumerate(sections, start=1):
            path = s.get("section_path") or "—"
            body = (s.get("excerpt") or s.get("snippet") or "").strip()
            body = body[:3000]  # safety cap per section
            parts.append(f"[Источник {i} · {path}]\n{body}\n")
    return "\n".join(parts)


def generate_summary(
    *,
    exam: Exam,
    theme_code: str,
    theme_name: str,
    chapter_name: str | None,
    sections: list[dict],
    llm_generator,
    tasks: list[dict] | None = None,
    concepts: list[dict] | None = None,
) -> ThemeSummary:
    """Generate a clean theory summary grounded on the theme's actual tasks.

    ``concepts`` are the concepts the theme's tasks actually test (ranked by
    the ``TESTS_CONCEPT`` signal), each ``{term, definition}``. ``tasks`` are a
    small sample of the real questions, each ``{task_text, correct}``. Together
    they steer the summary toward exactly what the student will be asked — see
    ``get_theme_article``.
    """
    hash_ = _content_hash(theme_name, sections, tasks, concepts)
    cached = get_cached(exam, theme_code, hash_)
    if cached is not None:
        return cached

    # Nothing to ground on at all → honest placeholder.
    if not sections and not concepts and not tasks:
        out = "В учебнике пока нет материала по этой теме."
        save_cache(exam, theme_code, out, hash_)
        return ThemeSummary(summary_md=out, cached=False, generated_at=time.time())

    settings = get_settings()
    client = llm_generator._client  # noqa: SLF001 — pragmatic reuse
    user = _user_prompt(chapter_name, theme_name, sections, tasks, concepts)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    started = time.time()
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            max_completion_tokens=900,
            messages=messages,
        )
    except TypeError:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=900,
            messages=messages,
        )
    md = (resp.choices[0].message.content or "").strip()
    if not md:
        md = "Не удалось собрать объяснение по этой теме."
    save_cache(exam, theme_code, md, hash_)
    logger.info(
        "Theme summary built for %s/%s in %.1fs (%d chars)",
        exam.slug, theme_code, time.time() - started, len(md),
    )
    return ThemeSummary(summary_md=md, cached=False, generated_at=time.time())
