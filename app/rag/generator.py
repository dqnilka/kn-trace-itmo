"""Theory-content generator.

Default mode is `llm`: synthesizes a structured Markdown explanation using
Yandex Eliza (OpenAI-compatible API at https://api.eliza.yandex.net/openai/v1)
with model `gpt-5.4-nano`. Bearer auth via SOY_TOKEN.

Strict policy: never fabricate facts outside the supplied retrieved context;
if context is empty, the generator emits a short "context not found" message.

`extractive` mode is used **only** when explicitly requested via the
`Generator.generate(..., mode='extractive')` argument (e.g. from unit tests
when SKIP_LLM=1). Per product decision the public API does NOT silently fall
back to extractive on LLM failure; instead, an exception is raised and the
service layer surfaces it as 502/503.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.api.schemas import Source
from app.core.config import get_settings
from app.core.logging import get_logger
from app.graph.knowledge_graph import ExpansionResult, GraphNode
from app.rag.retriever import RetrievedDoc

logger = get_logger(__name__)

GenMode = Literal["llm", "extractive"]


# ---------- Question shape detection ----------

# Regex for "1.", "2)", "I.", "II)" lines with following text — typical multiple-choice option markers.
_OPTION_LINE_RE = re.compile(r"^\s*(?:\d{1,2}|[IVX]{1,4})[.)]\s+\S", re.MULTILINE)
_OPTIONS_KEYWORD_RE = re.compile(r"(?im)^\s*(варианты|options)\s*:\s*$")
_ANSWER_KEYWORD_RE = re.compile(r"(?im)^\s*(ответ|answer)\s*:\s*\S")


def detect_multiple_choice(question_text: str) -> bool:
    """Detect whether the question is a multiple-choice item with explicit options.

    Heuristics: at least 3 option-marker lines OR an explicit "Варианты:" keyword.
    """
    if not question_text:
        return False
    if _OPTIONS_KEYWORD_RE.search(question_text):
        return True
    n_options = len(_OPTION_LINE_RE.findall(question_text))
    return n_options >= 3


def extract_correct_answer(question_text: str) -> str | None:
    """Extract the 'Ответ: ...' line if present (k2-18 questions sometimes embed answers)."""
    m = re.search(r"(?im)^\s*ответ\s*:\s*(.+)$", question_text)
    return m.group(1).strip() if m else None


def extract_options(question_text: str) -> list[str]:
    """Extract option lines like "1. ...", "I. ...", etc. from a multiple-choice question.

    Returns a list of clean option strings (without the leading marker).
    Stops at the "Ответ:" / "Answer:" line so the answer text is not mixed in.
    """
    if not question_text:
        return []
    # Cut off everything starting from 'Ответ:' / 'Answer:'
    cut = re.split(r"(?im)^\s*(?:ответ|answer)\s*:", question_text, maxsplit=1)[0]
    options: list[str] = []
    for m in re.finditer(
        r"(?m)^\s*(?:(\d{1,2})|([IVX]{1,4}))[.)]\s+(\S.*?)\s*$",
        cut,
    ):
        text = m.group(3).strip()
        # Filter out very short fragments (e.g. accidental matches in headings)
        if len(text) >= 5:
            options.append(text)
    return options


@dataclass
class GeneratedTheory:
    text: str
    sources: list[Source]
    mode: GenMode


SYSTEM_PROMPT_RU = """Ты — преподаватель курса подготовки к экзамену ФСФР (рынок ценных бумаг).
Твоя задача — объяснить тему вопроса, в котором студент ошибся, используя ТОЛЬКО предоставленный контекст из учебной базы.
Запрещено: придумывать факты, добавлять цифры, законы или определения, отсутствующие в контексте.
Структура ответа (строго в Markdown):
1. **Что проверял вопрос** — 1-2 предложения.
2. **Ключевые понятия** — маркированный список с краткими определениями (бери определения из контекста).
3. **Подробное объяснение** — связный текст 5-10 предложений, опираясь на фрагменты контекста.
4. **На что обратить внимание** — 2-3 короткие подсказки/типичные ошибки.
Пиши на русском языке. Не цитируй идентификаторы вида 'theory_economics:...' и не указывай источники в тексте — это сделает система отдельно."""

# Overlay appended when the question is detected as multiple-choice.
# It REPLACES the abstract step "Подробное объяснение" with a per-option breakdown.
MULTIPLE_CHOICE_OVERLAY_RU = """ВАЖНО: данный вопрос — с вариантами ответа.
Замени секцию «Подробное объяснение» на раздел «**Разбор вариантов**»:
- перечисли каждый вариант (1, 2, 3, ...) и для КАЖДОГО кратко (1-3 предложения) укажи, верен он или нет и ПОЧЕМУ — со ссылкой на конкретный механизм/правило из контекста.
- если в задании указан правильный ответ ('Ответ: ...'), явно подтверди его в начале раздела фразой «Правильный ответ: ...».
- избегай тавтологии: не объясняй вариант через переформулирование самого варианта; объясняй через определение из контекста.
- не выдумывай нумерацию или варианты, которых нет в задании."""

# Overlay appended when the question text is a "compound" topic block — many themes joined.
# We detect this when retrieved Concept nodes span multiple disconnected definitions.
COMPOUND_QUESTION_OVERLAY_RU = """ВАЖНО: вопрос затрагивает несколько подтем.
В секции «Подробное объяснение» обязательно охвати каждую подтему отдельным абзацем (по 2-4 предложения). 
Если по какой-то подтеме контекста не хватает, явно напиши «по подтеме <N> в предоставленном контексте недостаточно материала», 
вместо общих фраз — это полезно студенту, чтобы знать пробел."""


class Generator:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: float = 60.0,
        max_tokens: int = 1200,
        ca_bundle: str | None = None,
    ) -> None:
        import httpx
        from openai import OpenAI

        self._model = model
        self._max_tokens = max_tokens

        verify: bool | str = True
        if ca_bundle:
            verify = ca_bundle
        http_client = httpx.Client(verify=verify, timeout=timeout_s)
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            timeout=timeout_s,
        )
        logger.info(
            "LLM client configured (base_url=%s, model=%s, ca_bundle=%s)",
            base_url, model, ca_bundle or "(default)",
        )

    @classmethod
    def from_settings(cls) -> "Generator":
        settings = get_settings()
        key = settings.effective_api_key
        if not key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Export LLM_API_KEY (or legacy SOY_TOKEN) "
                "in your shell before launching the service. See .env.example for "
                "supported providers (OpenAI / OpenRouter / DeepSeek / YandexGPT)."
            )
        # Защита от типичной ошибки: в .env вместо настоящего ключа оставлен
        # русскоязычный плейсхолдер ("по хорошему вставить токен..."). httpx
        # позже всё равно упадёт на header.encode("ascii"), но к тому моменту
        # уже прогружены модели и сожжено пара минут. Ловим сразу.
        if not key.isascii():
            raise RuntimeError(
                "LLM_API_KEY contains non-ASCII characters — похоже на "
                "placeholder вместо реального ключа. Проверьте .env, замените "
                "на настоящий ключ (sk-...) или поставьте SKIP_LLM=true для "
                "запуска без LLM (extractive fallback)."
            )
        if not settings.llm_base_url.isascii():
            raise RuntimeError(
                "LLM_BASE_URL contains non-ASCII characters. Проверьте .env."
            )
        return cls(
            api_key=key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
            ca_bundle=settings.llm_ca_bundle,
        )

    # ---------- public API ----------

    def generate(
        self,
        question_node: GraphNode,
        expansion: ExpansionResult,
        retrieved: list[RetrievedDoc],
        mode: GenMode = "llm",
    ) -> GeneratedTheory:
        sources = self._build_sources(retrieved)
        if mode == "extractive" or get_settings().skip_llm:
            text = self._extractive(question_node, expansion, retrieved)
            return GeneratedTheory(text=text, sources=sources, mode="extractive")
        text = self._llm(question_node, expansion, retrieved)
        return GeneratedTheory(text=text, sources=sources, mode="llm")

    # ---------- internals ----------

    def _build_sources(self, retrieved: list[RetrievedDoc], max_sources: int = 8) -> list[Source]:
        out: list[Source] = []
        for d in retrieved[:max_sources]:
            out.append(
                Source(
                    node_id=d.node_id,
                    node_type=d.node_type,  # type: ignore[arg-type]
                    score=round(d.score, 4),
                    snippet=d.snippet,
                )
            )
        return out

    def _build_context_block(self, retrieved: list[RetrievedDoc], max_chars: int = 6000) -> str:
        """Render retrieved docs as a single string for the LLM prompt."""
        lines: list[str] = []
        used = 0
        for i, d in enumerate(retrieved, start=1):
            type_label = {
                "Concept": "Понятие",
                "Chunk": "Фрагмент учебника",
                "MdChunk": "Раздел учебника",
            }.get(d.node_type, d.node_type)
            section = ""
            if d.metadata.get("section_path"):
                section = f" [{d.metadata['section_path']}]"
            block = f"[{i}] ({type_label}){section}\n{d.text.strip()}"
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block) + 2
        return "\n\n".join(lines) if lines else "(контекст пуст)"

    def _build_system_prompt(
        self,
        question_node: GraphNode,
        expansion: ExpansionResult,
    ) -> str:
        """Choose system prompt: base + optional overlays for question shape."""
        prompt = SYSTEM_PROMPT_RU
        if detect_multiple_choice(question_node.text):
            prompt = prompt + "\n\n" + MULTIPLE_CHOICE_OVERLAY_RU
        # Compound-topic detection: many distinct concepts hit at depth 1.
        l1_concepts = sum(
            1 for it in expansion.items
            if it.depth == 1 and it.node.type == "Concept"
        )
        if l1_concepts >= 5:
            prompt = prompt + "\n\n" + COMPOUND_QUESTION_OVERLAY_RU
        return prompt

    def _llm(
        self,
        question_node: GraphNode,
        expansion: ExpansionResult,
        retrieved: list[RetrievedDoc],
    ) -> str:
        context_block = self._build_context_block(retrieved)
        graph_topics: list[str] = []
        for it in expansion.top(5):
            if it.node.type == "Concept" and it.node.text:
                graph_topics.append(it.node.text)
        related_summary = ", ".join(graph_topics[:5]) if graph_topics else "—"

        system_prompt = self._build_system_prompt(question_node, expansion)
        is_mc = detect_multiple_choice(question_node.text)
        correct_answer = extract_correct_answer(question_node.text) if is_mc else None

        user_lines = [
            f"Вопрос, в котором ошибся студент:\n\"\"\"\n{question_node.text.strip()}\n\"\"\"",
            f"Связанные понятия из графа знаний: {related_summary}",
        ]
        if correct_answer:
            user_lines.append(f"Указанный в задании правильный ответ: {correct_answer}")
        user_lines.append(f"Контекст из учебника:\n{context_block}")
        user_msg = "\n\n".join(user_lines)

        logger.info(
            "LLM call: q=%s, multiple_choice=%s, has_answer=%s, ctx_chars=%d",
            question_node.id, is_mc, bool(correct_answer), len(context_block),
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_completion_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
        except TypeError:
            # Older API — fall back to max_tokens
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
        content = resp.choices[0].message.content or ""
        return content.strip()

    def _extractive(
        self,
        question_node: GraphNode,
        expansion: ExpansionResult,
        retrieved: list[RetrievedDoc],
    ) -> str:
        """Deterministic concatenation of top-N retrieved fragments — no LLM."""
        lines: list[str] = []
        lines.append("**Что проверял вопрос**")
        lines.append(question_node.text.strip())
        lines.append("")
        # Concepts (definitions)
        concept_docs = [d for d in retrieved if d.node_type == "Concept"][:5]
        if concept_docs:
            lines.append("**Ключевые понятия**")
            for d in concept_docs:
                lines.append(f"- {d.text.strip()}")
            lines.append("")
        chunk_docs = [d for d in retrieved if d.node_type in ("Chunk", "MdChunk")][:4]
        if chunk_docs:
            lines.append("**Подробное объяснение**")
            for d in chunk_docs:
                lines.append(d.text.strip())
                lines.append("")
        if not concept_docs and not chunk_docs:
            lines.append("_Не удалось извлечь релевантную теорию из базы._")
        return "\n".join(lines).strip()
