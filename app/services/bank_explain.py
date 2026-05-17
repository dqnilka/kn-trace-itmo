"""LLM-разбор задачи из банка экзамена.

В отличие от старого ``analyze_test``, эта реализация не зависит от
``KnowledgeGraph`` (там были k2-18 Assessment-узлы). Здесь:
  1. Ищем задачу по ``task_id`` в bank.json экзамена.
  2. Берём query = ``task_text + правильный вариант + (опц.) название темы``.
  3. RAG-поиск по коллекциям, заявленным в манифесте (``md_chunks`` + по
     желанию ``graph_chunks``) — без BFS по графу.
  4. Передаём в LLM с фокусным промптом: «объясни задачу, разбери варианты,
     если возможно — укажи в чём ошибка выбранного варианта».
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.api.schemas import ExplainResponse, Source
from app.core.config import get_settings
from app.core.logging import get_logger
from app.exams.registry import Exam, load_bank
from app.rag.embeddings import BaseEmbedder
from app.rag.vectorstore import Hit, VectorStore

logger = get_logger(__name__)


class UnknownBankTaskError(KeyError):
    """Raised when a task_id is not present in the exam's bank."""


@dataclass
class _RetrievedContext:
    """Hits across all configured collections + chosen task metadata."""

    task: dict
    theme: dict | None
    chapter: dict | None
    hits: list[tuple[str, Hit]]  # (source_collection, hit)


SYSTEM_PROMPT_RU = """Ты — преподаватель курса подготовки к экзамену.
Тебе нужно объяснить студенту его ошибку в тестовом задании, используя ТОЛЬКО предоставленный контекст из учебника.
Категорически запрещено: придумывать факты, цифры, нормы или определения, которых нет в контексте.
Если контекста не хватает — честно скажи «в предоставленном контексте недостаточно материала по этому пункту», вместо общих слов.

Структура ответа (строго в Markdown):
1. **Правильный ответ** — назови вариант (буква/номер) и короткое определение из контекста.
2. **Разбор вариантов** — перечисли КАЖДЫЙ вариант (1, 2, 3, …): помечай ✓ верный и ✗ неверные, и для каждого 1-2 предложения, почему — со ссылкой на конкретный механизм из контекста.
3. **Почему выбранный вариант неверен** — если студент выбрал не тот вариант, акцентируй разницу между его выбором и правильным.
4. **Что повторить** — 1-2 темы/понятия из контекста, на которые опирается задача.

Пиши на русском языке. Не цитируй идентификаторы вида 'theory_economics:...' и не указывай источники в тексте — это сделает система отдельно."""


def _build_indexes(bank: dict) -> tuple[dict[int, dict], dict[str, dict], dict[int, dict]]:
    tasks_by_id = {t["id"]: t for t in bank.get("tasks", [])}
    themes_by_code = {t["code"]: t for t in bank.get("themes", [])}
    chapters_by_id = {c["id"]: c for c in bank.get("chapters", [])}
    return tasks_by_id, themes_by_code, chapters_by_id


def _format_options(options: list[dict]) -> str:
    lines = []
    for o in options:
        marker = "✓" if o.get("is_correct") else " "
        lines.append(f"{marker} {o.get('label')}. {o.get('text','').strip()}")
    return "\n".join(lines)


def _query_text(task: dict, theme: dict | None) -> str:
    parts: list[str] = []
    if theme:
        parts.append(f"Тема: {theme.get('name', '')}")
    parts.append((task.get("task_text") or "").strip())
    correct = next((o for o in task.get("options", []) if o.get("is_correct")), None)
    if correct:
        parts.append(f"Правильный ответ: {correct.get('text', '')}")
    return "\n".join(p for p in parts if p)


@lru_cache(maxsize=8)
def _load_theme_sections(exam_root: str) -> dict[str, list[dict]]:
    """Cache theme_sections.json keyed by exam dir.

    Returns ``{theme_code: [{chunk_id, section_path, snippet, score}, ...]}``
    or empty dict if not yet built. Cache busts when the file path changes.
    """
    p = Path(exam_root) / "theme_sections.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return dict(data.get("by_theme") or {})
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to read %s: %s", p, e)
        return {}


def _retrieve(
    *,
    exam: Exam,
    bank: dict,
    task_id: int,
    embedder: BaseEmbedder,
    store: VectorStore,
) -> _RetrievedContext:
    tasks, themes, chapters = _build_indexes(bank)
    if task_id not in tasks:
        raise UnknownBankTaskError(task_id)
    task = tasks[task_id]
    theme = themes.get(task.get("theme_code"))
    chapter = chapters.get(theme.get("chapter_id")) if theme else None

    query = _query_text(task, theme)
    q_emb = embedder.encode([query], mode="query")[0]

    hits: list[tuple[str, Hit]] = []
    for col in exam.rag_collections:
        try:
            results = store.search(col, q_emb, top_k=exam.rag_top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning("Collection %r unavailable: %s", col, e)
            continue
        for h in results:
            hits.append((col, h))

    # de-dup by id, keep best score
    by_id: dict[str, tuple[str, Hit]] = {}
    for col, h in hits:
        prev = by_id.get(h.id)
        if prev is None or h.score > prev[1].score:
            by_id[h.id] = (col, h)
    deduped = list(by_id.values())

    # Boost chunks pre-linked to this task's theme via theme_sections.json
    theme_code = task.get("theme_code")
    if theme_code:
        ts = _load_theme_sections(str(exam.root))
        theme_hits = {s.get("chunk_id"): s for s in ts.get(str(theme_code), [])}
        if theme_hits:
            boosted: list[tuple[str, Hit]] = []
            for col, h in deduped:
                if h.id in theme_hits:
                    # Smooth boost — preserves ordering within the boosted set.
                    h = Hit(
                        id=h.id,
                        score=min(1.0, h.score + 0.18 * (1.0 - h.score)),
                        text=h.text,
                        metadata=h.metadata,
                    )
                boosted.append((col, h))
            # Inject any theme-mapped chunks the vector search missed entirely
            # (top 3 of them — diminishing returns).
            present = {h.id for _, h in boosted}
            for s in list(theme_hits.values())[:3]:
                cid = s.get("chunk_id")
                if cid and cid not in present:
                    boosted.append(
                        (
                            "md_chunks",
                            Hit(
                                id=cid,
                                score=float(s.get("score") or 0.5),
                                text=str(s.get("snippet", "")),
                                metadata={
                                    "section_path": s.get("section_path", ""),
                                    "char_offset": s.get("char_offset", 0),
                                    "source": "theme_sections",
                                },
                            ),
                        )
                    )
            deduped = boosted

    deduped.sort(key=lambda x: x[1].score, reverse=True)
    return _RetrievedContext(task=task, theme=theme, chapter=chapter, hits=deduped)


def _context_block(hits: Iterable[tuple[str, Hit]], max_chars: int = 6000) -> str:
    used = 0
    out: list[str] = []
    for i, (col, h) in enumerate(hits, start=1):
        body = (h.text or "").strip()
        if not body:
            continue
        chunk = f"[Источник {i} · {col}]\n{body}"
        if used + len(chunk) > max_chars and out:
            break
        out.append(chunk)
        used += len(chunk)
    return "\n\n".join(out)


def _build_user_prompt(ctx: _RetrievedContext, picked_label: str | None) -> str:
    task = ctx.task
    theme = ctx.theme
    chapter = ctx.chapter
    correct = next(
        (o for o in task.get("options", []) if o.get("is_correct")), None
    )
    correct_label = (correct or {}).get("label", "")
    picked_text = ""
    if picked_label:
        picked = next(
            (o for o in task.get("options", []) if o.get("label") == picked_label),
            None,
        )
        if picked:
            picked_text = (
                f"\nСтудент выбрал вариант **{picked_label}**: "
                f"«{picked.get('text','').strip()}»."
            )

    location = []
    if chapter:
        location.append(f"Глава {chapter.get('num')}. {chapter.get('name')}")
    if theme:
        location.append(f"Тема {theme.get('code')}. {theme.get('name')}")
    location_md = " · ".join(location)

    question = (task.get("task_text") or "").strip()
    options_md = _format_options(task.get("options", []))
    context_md = _context_block(ctx.hits) or "(контекст пуст)"

    return (
        f"{location_md}\n\n"
        f"## Задача\n{question}\n\n"
        f"## Варианты\n{options_md}\n\n"
        f"Правильный вариант: **{correct_label}**.{picked_text}\n\n"
        f"## Контекст из учебника\n{context_md}"
    )


def explain_bank_task(
    *,
    exam: Exam,
    task_id: int,
    picked_label: str | None,
    embedder: BaseEmbedder,
    store: VectorStore,
    llm_generator,
) -> ExplainResponse:
    """Orchestrates RAG + LLM explanation for a single bank task.

    ``llm_generator`` is the existing :class:`app.rag.generator.Generator`; we
    only use its underlying client. We don't reuse :meth:`Generator.generate`
    because it's tied to ``ExpansionResult``.
    """
    bank = load_bank(exam)
    ctx = _retrieve(
        exam=exam,
        bank=bank,
        task_id=task_id,
        embedder=embedder,
        store=store,
    )
    correct = next((o for o in ctx.task.get("options", []) if o.get("is_correct")), None)
    correct_label = (correct or {}).get("label", "")
    is_correct = picked_label is not None and picked_label == correct_label

    sources: list[Source] = []
    for col, h in ctx.hits[:8]:
        node_type = "MdChunk" if col == "md_chunks" else (
            "Chunk" if col == "graph_chunks" else "Concept"
        )
        sources.append(
            Source(
                node_id=h.id,
                node_type=node_type,  # type: ignore[arg-type]
                score=round(h.score, 4),
                snippet=(h.text or "")[:400],
            )
        )

    settings = get_settings()
    if settings.skip_llm:
        explanation = _extractive_fallback(ctx, picked_label)
        mode = "extractive"
    else:
        prompt = _build_user_prompt(ctx, picked_label)
        try:
            explanation = _call_llm(llm_generator, prompt)
            mode = "llm"
        except Exception as e:  # noqa: BLE001
            logger.exception("LLM explain failed: %s", e)
            raise

    return ExplainResponse(
        task_id=task_id,
        theme_code=ctx.task.get("theme_code", ""),
        chapter_name=(ctx.chapter or {}).get("name"),
        theme_name=(ctx.theme or {}).get("name"),
        correct_label=correct_label,
        picked_label=picked_label,
        is_correct=is_correct,
        explanation_md=explanation,
        sources=sources,
        generation_mode=mode,  # type: ignore[arg-type]
    )


def _call_llm(generator, user_prompt: str) -> str:
    """Минимальный вызов чат-комплитов: тот же клиент, что и у Generator."""
    settings = get_settings()
    client = generator._client  # noqa: SLF001 — pragmatic reuse
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_RU},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            max_completion_tokens=settings.llm_max_tokens,
            messages=messages,
        )
    except TypeError:
        response = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            messages=messages,
        )
    return (response.choices[0].message.content or "").strip()


def _extractive_fallback(ctx: _RetrievedContext, picked_label: str | None) -> str:
    lines = ["## Правильный ответ"]
    correct = next((o for o in ctx.task.get("options", []) if o.get("is_correct")), None)
    if correct:
        lines.append(f"**{correct['label']}.** {correct.get('text','')}")
    if picked_label and picked_label != (correct or {}).get("label"):
        lines.append(f"\n*Студент выбрал вариант {picked_label}.*")
    if ctx.hits:
        lines.append("\n## Релевантный фрагмент учебника")
        lines.append((ctx.hits[0][1].text or "").strip()[:1500])
    return "\n".join(lines)
