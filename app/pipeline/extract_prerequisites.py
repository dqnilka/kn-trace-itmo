"""LLM extraction of PREREQUISITE edges between concepts.

Strategy: group concepts by chapter (via ``BELONGS_TO_THEME → Theme.chapter_id``)
and ask GPT, per chapter, "which concepts in this list are prerequisites for
which others?" Output: directed edges ``co:A → co:B`` meaning "you must know A
before you can really learn B".

Why per-chapter (not whole graph at once):
  * Each chapter has 30-150 concepts → comfortable single prompt
  * LLM stays focused on a coherent topic, less hallucination
  * 13 chapters × 1 call = 13 LLM calls total (cheap, ~$0.2)

Cross-chapter prereqs (e.g. chapter 3 → chapter 1) are NOT extracted by this
step. Two reasons:
  1. Curriculum order in the bank already implies them (chapters are numbered).
  2. Adding all-pairs would blow up the prompt and yield noisier results.

Output: list of ``ConceptPrereqLink`` (from_concept_id, to_concept_id, score,
reason). Score is currently fixed at 1.0 (LLM yes/no) — we can replace with
log-prob confidence later if needed.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConceptPrereqLink:
    from_concept_id: str  # must-know-first
    to_concept_id: str    # depends-on
    chapter_id: int
    score: float = 1.0
    reason: str = ""


@dataclass
class PrereqUsage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    failed: int = 0


SYSTEM_PROMPT = """Ты — методист курса. Тебе дают список концептов из одной главы учебника и нужно найти PREREQUISITE-связи между ними.

PREREQUISITE(A, B) означает: «нельзя нормально освоить B, не зная A». Это ОТНОШЕНИЕ ПОРЯДКА: если без A нельзя понять B, нет смысла подсовывать B пока A не понят.

ПРАВИЛА:
- Только сильные связи. Если A лишь «упоминается» рядом с B — это НЕ prerequisite.
- НЕ выбирай связи в обе стороны (A→B и B→A). Если сомневаешься — оставь одну.
- НЕ выдумывай транзитивные связи (если A→B и B→C, не добавляй A→C — это уже выводится).
- Если концепт частный случай другого (subclass), это ПРЕРЕКВИЗИТ родительского концепта для частного: общее → частное.
- Если ни одна пара не подходит — верни пустой массив.

Формат ответа (СТРОГИЙ JSON, без preamble):
{"prereqs": [
  {"from": "<concept_id_A>", "to": "<concept_id_B>", "reason": "очень короткое объяснение (1-2 слова)"},
  ...
]}"""


def _build_user_payload(chapter_id: int, chapter_name: str, concepts: list[dict]) -> str:
    return json.dumps(
        {
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "concepts": [
                {
                    "id": c["id"],
                    "term": c.get("term") or c["id"],
                    "definition": (c.get("definition") or "")[:300],
                }
                for c in concepts
            ],
        },
        ensure_ascii=False,
    )


def _parse_response(text: str) -> list[dict]:
    if not text:
        return []
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object in response")
    payload = json.loads(text[start : end + 1])
    out: list[dict] = []
    for row in payload.get("prereqs", []):
        f = row.get("from")
        t = row.get("to")
        if not f or not t or f == t:
            continue
        out.append({"from": str(f), "to": str(t), "reason": (row.get("reason") or "")[:120]})
    return out


def _call_llm(client: Any, model: str, user_payload: str, max_tokens: int) -> tuple[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    try:
        resp = client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=messages,
        )
    except TypeError:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
    return (resp.choices[0].message.content or "").strip(), resp


def extract_prerequisites(
    *,
    graph: dict,
    llm_generator,
    max_tokens: int = 3000,
    max_retries: int = 2,
) -> tuple[list[ConceptPrereqLink], PrereqUsage]:
    """Walk concepts grouped by chapter, LLM-extract prereq edges per chapter.

    ``graph`` is the in-memory unified graph (matches the schema written by
    ``app/pipeline/strict.py:assemble_graph``).
    """
    settings = get_settings()
    client = llm_generator._client  # noqa: SLF001 — pragmatic reuse
    model = settings.llm_model

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    chapters_by_id: dict[int, dict] = {}
    themes_by_code: dict[str, dict] = {}
    concepts_by_id: dict[str, dict] = {}
    for n in nodes:
        if n.get("type") == "Chapter":
            chapters_by_id[int(n.get("num") or 0)] = n
        elif n.get("type") == "Theme":
            themes_by_code[str(n.get("code"))] = n
        elif n.get("type") == "Concept":
            cid = str(n.get("id", "")).removeprefix("co:")
            concepts_by_id[cid] = {
                "id": cid,
                "term": n.get("term"),
                "definition": n.get("definition"),
            }

    # concept → chapter via BELONGS_TO_THEME
    concept_chapter: dict[str, int] = {}
    for e in edges:
        if e.get("type") != "BELONGS_TO_THEME":
            continue
        cid = str(e.get("source") or "").removeprefix("co:")
        tcode = str(e.get("target") or "").removeprefix("th:")
        theme = themes_by_code.get(tcode)
        if not theme:
            continue
        chap_id = int(theme.get("chapter_id") or 0)
        if chap_id > 0:
            concept_chapter[cid] = chap_id

    grouped: dict[int, list[dict]] = defaultdict(list)
    for cid, chid in concept_chapter.items():
        c = concepts_by_id.get(cid)
        if c:
            grouped[chid].append(c)

    usage = PrereqUsage()
    out: list[ConceptPrereqLink] = []
    started = time.time()

    for chid in sorted(grouped.keys()):
        concepts = grouped[chid]
        chap_node = next(
            (n for n in nodes if n.get("type") == "Chapter" and int(n.get("id", "ch:0").removeprefix("ch:")) == chid),
            None,
        )
        chap_name = (chap_node or {}).get("name") or f"Chapter {chid}"
        if len(concepts) < 2:
            logger.info("Chapter %d (%s): too few concepts (%d) — skipping", chid, chap_name, len(concepts))
            continue

        payload = _build_user_payload(chid, chap_name, concepts)
        parsed: list[dict] | None = None
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                text, resp = _call_llm(client, model, payload, max_tokens)
                parsed = _parse_response(text)
                usage.requests += 1
                u = getattr(resp, "usage", None)
                if u is not None:
                    usage.input_tokens += getattr(u, "prompt_tokens", 0) or 0
                    usage.output_tokens += getattr(u, "completion_tokens", 0) or 0
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(
                    "Chapter %d prereq extract failed (attempt %d/%d): %s",
                    chid, attempt + 1, max_retries + 1, e,
                )
                time.sleep(1.5 * (attempt + 1))
        if parsed is None:
            usage.failed += 1
            logger.error("Chapter %d giving up: %s", chid, last_err)
            continue

        known = {c["id"] for c in concepts}
        kept = 0
        for row in parsed:
            f, t = row["from"], row["to"]
            # Models often return ids with or without our "co:" prefix
            f_norm = f.removeprefix("co:")
            t_norm = t.removeprefix("co:")
            if f_norm not in known or t_norm not in known:
                logger.debug("Chapter %d: rejected pair (%s → %s) — unknown id", chid, f, t)
                continue
            out.append(
                ConceptPrereqLink(
                    from_concept_id=f_norm,
                    to_concept_id=t_norm,
                    chapter_id=chid,
                    score=1.0,
                    reason=row.get("reason", ""),
                )
            )
            kept += 1
        logger.info(
            "Chapter %d (%s): %d concepts → %d prereq edges (LLM proposed %d)",
            chid, chap_name, len(concepts), kept, len(parsed),
        )

    usage.elapsed_s = round(time.time() - started, 1)
    logger.info(
        "Prereq extraction done: %d edges across %d chapters · %d reqs · %.1fs · %d failed",
        len(out), len(grouped), usage.requests, usage.elapsed_s, usage.failed,
    )
    return out, usage
