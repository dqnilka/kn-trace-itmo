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


SYSTEM_PROMPT = """Ты — опытный методист-репетитор курса подготовки к экзамену ФСФР. На вход получаешь: НАЗВАНИЕ темы; перечень понятий, которые встречаются в заданиях темы (с определениями); примеры заданий; секции учебника. Задача — написать понятный методический разбор темы, который реально учит и даёт решать задания.

ГЛАВНЫЙ ПРИНЦИП — КАРКАС, А НЕ СОЛЯНКА:
- Веди строго от НАЗВАНИЯ темы. Сначала дай СИСТЕМУ/КЛАССИФИКАЦИЮ темы: по каким основаниям делится предмет (например, для «виды ценных бумаг» — по форме выпуска: документарные/бездокументарные; по типу прав: долевые/долговые; эмиссионные/неэмиссионные; именные/ордерные/предъявительские). Понятия из списка ВПИСЫВАЙ как элементы этой системы и группируй по смыслу.
- НЕ вываливай плоский список разнородных терминов. Узкие/периферийные понятия (например, складское свидетельство, варрант, чек) упоминай только как примеры внутри нужной ветки классификации, кратко, не делая их центром.
- Центральное — вперёд; периферию — сжать или опустить.

СОДЕРЖАНИЕ И ДОСТОВЕРНОСТЬ:
- Факты бери из предоставленных определений и секций. Свободно реорганизуй и обобщай их в каркас, но НЕ выдумывай цифры, сроки, проценты, нормы и определения, которых нет в контексте.
- Пиши так, чтобы после прочтения студент мог решить типовое задание темы сам — объясняй логику и различия между близкими понятиями.

СТРУКТУРА — АДАПТИВНАЯ (строгий Markdown, без заголовков # и ##; секции выделяй **жирным**, используй списки). Набор и длина блоков зависят от темы: простую тему — короче (200–300 слов), сложную/с многими понятиями — подробнее (до ~600). Ориентир по блокам:

**Суть и классификация** — что это за тема и по каким основаниям всё делится (каркас). Это ядро разбора.

**Ключевые понятия** — термины из списка, разложенные ПО этому каркасу (можно подзаголовками-**жирным** по группам): **термин** — определение + чем отличается от соседних.

**На что обратить внимание / ловушки** — где путаются, какие близкие понятия смешивают, что любят спрашивать (вплетай сюда экзаменационный аспект, отдельный блок «как спрашивают» не делай).

**Запомнить** — 3–5 коротких тезисов-чеклист.

Блок с разбором конкретного примера задания добавляй ТОЛЬКО если он реально проясняет тему; иначе не добавляй.

ТОН: русский, как хороший репетитор — живо, по делу, уверенно; без воды, без «играет важную роль в экономике», без «как видно из контекста», без канцелярита. Если материала в учебнике мало — честно скажи и разбери что есть, короче."""


@dataclass
class ThemeSummary:
    summary_md: str
    cached: bool
    generated_at: float


def _cache_paths(
    exam: Exam, theme_code: str, variant: str | None = None
) -> tuple[Path, Path]:
    base = exam.root / "theme_summaries"
    stem = f"{theme_code}__{variant}" if variant else theme_code
    return base / f"{stem}.md", base / f"{stem}.meta.json"


def _content_hash(
    theme_name: str,
    sections: list[dict],
    tasks: list[dict] | None = None,
    concepts: list[dict] | None = None,
) -> str:
    h = hashlib.sha256()
    # Prompt-version tag: bump when the grounding strategy changes so stale
    # task-agnostic summaries are regenerated rather than served from cache.
    h.update(b"v5-framework\n")
    h.update(theme_name.encode("utf-8"))
    for s in sections:
        h.update((s.get("section_path", "") + "\n" + s.get("excerpt", "")).encode("utf-8"))
    for c in concepts or []:
        h.update((str(c.get("term", "")) + "\n" + str(c.get("definition", ""))).encode("utf-8"))
    for t in tasks or []:
        h.update((str(t.get("task_text", "")) + "\n" + str(t.get("correct", ""))).encode("utf-8"))
    return h.hexdigest()[:16]


def get_cached(
    exam: Exam, theme_code: str, hash_: str, variant: str | None = None
) -> ThemeSummary | None:
    md_path, meta_path = _cache_paths(exam, theme_code, variant)
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
    variant: str | None = None,
) -> None:
    md_path, meta_path = _cache_paths(exam, theme_code, variant)
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


import re

# Textbook artifacts that make raw excerpts look "сырыми" — strip before the LLM
# sees them so the summary is built from clean text.
_PAGE_MARKER_RE = re.compile(r"\{\s*\d+\s*\}-*")          # {378}--------
_SECTION_NUM_RE = re.compile(r"(?m)^\s*\d+(?:\.\d+)+\.?\s*")  # leading "16.5.2 "
_SPACED_CAPS_RE = re.compile(r"\b([А-ЯЁ])\s+(?=[А-ЯЁ]\b)")  # "РАЗДЕЛ ТРЕТИ Й"
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINL_RE = re.compile(r"\n{3,}")


def _clean_excerpt(text: str) -> str:
    """Remove page markers / section numbers / hyphenation noise from a raw
    textbook excerpt. Conservative — only strips well-known artifacts."""
    if not text:
        return ""
    t = _PAGE_MARKER_RE.sub(" ", text)
    t = t.replace("-\n", "")          # de-hyphenate line breaks
    t = _SECTION_NUM_RE.sub("", t)
    t = _SPACED_CAPS_RE.sub(r"\1", t)
    t = _MULTISPACE_RE.sub(" ", t)
    t = _MULTINL_RE.sub("\n\n", t)
    return t.strip()


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
        parts.append(
            "\nЗАДАНИЯ, которые студент увидит СРАЗУ ПОСЛЕ этой теории — "
            "подготовь именно к ним:\n"
        )
        for i, t in enumerate(tasks, start=1):
            q = str(t.get("task_text") or "").strip()[:500]
            correct = str(t.get("correct") or "").strip()[:300]
            block = f"[Задание {i}] {q}"
            if correct:
                block += f"\nВерный ответ: {correct}"
            parts.append(block)

    if sections:
        parts.append("\nСекции учебника (сырой источник, нужна чистка):\n")
        for i, s in enumerate(sections, start=1):
            path = s.get("section_path") or "—"
            body = _clean_excerpt((s.get("excerpt") or s.get("snippet") or ""))
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
    variant: str | None = None,
) -> ThemeSummary:
    """Generate a clean theory summary grounded on the theme's actual tasks.

    ``concepts`` are the concepts the theme's tasks actually test (ranked by
    the ``TESTS_CONCEPT`` signal), each ``{term, definition}``. ``tasks`` are a
    small sample of the real questions, each ``{task_text, correct}``. Together
    they steer the summary toward exactly what the student will be asked — see
    ``get_theme_article``. ``variant`` keys the cache for a specific task subset
    (a lesson grounded on exactly the tasks it will show).
    """
    hash_ = _content_hash(theme_name, sections, tasks, concepts)
    cached = get_cached(exam, theme_code, hash_, variant)
    if cached is not None:
        return cached

    # Nothing to ground on at all → honest placeholder.
    if not sections and not concepts and not tasks:
        out = "В учебнике пока нет материала по этой теме."
        save_cache(exam, theme_code, out, hash_, variant)
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
            max_completion_tokens=1600,
            messages=messages,
        )
    except TypeError:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=1600,
            messages=messages,
        )
    md = (resp.choices[0].message.content or "").strip()
    if not md:
        md = "Не удалось собрать объяснение по этой теме."
    save_cache(exam, theme_code, md, hash_, variant)
    logger.info(
        "Theme summary built for %s/%s in %.1fs (%d chars)",
        exam.slug, theme_code, time.time() - started, len(md),
    )
    return ThemeSummary(summary_md=md, cached=False, generated_at=time.time())
