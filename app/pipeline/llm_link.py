"""LLM rerank of task↔concept candidates.

Strategy:
  1. Embedding step (already done in ``link_tasks_to_concepts.py``) produces a
     top-K candidate list per task — fast, deterministic, but noisy. A high
     cosine score can come from surface lexical overlap.
  2. LLM rerank: we ask GPT, in batches, to pick the 1-3 candidates that the
     task ACTUALLY tests. Cheaper than asking the model to enumerate concepts
     from scratch, and it can't hallucinate concepts outside the candidate set.

Input: list of (task, [TaskConceptLink_candidate]) — typically top-K from
embedding linker.
Output: list of TaskConceptLink — at most 3 per task, with the LLM-assigned
score.

Cost on FSFR (2102 tasks, top-K=10, batch=10):
  ~210 LLM calls × ~3 KB prompt ≈ 600 KB input + 200 KB output → a few $ on
  the Eliza tier. Runtime: ~10-15 min depending on latency.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from app.core.config import get_settings
from app.core.logging import get_logger
from app.pipeline.link_tasks_to_concepts import TaskConceptLink

logger = get_logger(__name__)


SYSTEM_PROMPT = """Ты — методист курса подготовки к экзамену по финансовым рынкам.
Тебе дают учебные задачи и список концептов-кандидатов. Для каждой задачи укажи 1-3 концепта (из списка), которые она РЕАЛЬНО тестирует — то есть без понимания этого концепта правильный ответ не найти.

Категорически не выбирай концепты по поверхностному совпадению слов: если задача упоминает «облигация», а вариант ответа — про «вексель», то «облигация» НЕ тестируется.

Ответ строго в JSON-формате без пояснений:
{"links": [{"task_id": <int>, "concept_ids": ["<concept_id>", ...]}, ...]}

Не добавляй никакого текста до или после JSON.
Если ни один концепт не подходит — отдай пустой массив для этой задачи."""


@dataclass
class LLMUsage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    failed: int = 0


def _build_user_payload(
    batch: Sequence[tuple[dict, list[TaskConceptLink]]],
) -> str:
    out_tasks: list[dict] = []
    for task, candidates in batch:
        correct = next(
            (o for o in task.get("options", []) if o.get("is_correct")), None
        )
        out_tasks.append(
            {
                "task_id": int(task["id"]),
                "task_text": (task.get("task_text") or "").strip(),
                "correct_answer": (correct or {}).get("text", "").strip(),
                "candidates": [
                    {
                        "id": c.concept_id,
                        "term": c.concept_term,
                        "embedding_score": round(c.score, 3),
                    }
                    for c in candidates
                ],
            }
        )
    return json.dumps({"tasks": out_tasks}, ensure_ascii=False)


def _parse_response(text: str) -> dict[int, list[str]]:
    """Extract {task_id: [concept_id]} from the model response.

    Tolerant of model preamble / trailing junk: pulls the first JSON object.
    """
    if not text:
        return {}
    text = text.strip()
    # Strip Markdown code-fence if present.
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    # Find first JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object in LLM response")
    payload = json.loads(text[start : end + 1])
    out: dict[int, list[str]] = {}
    for row in payload.get("links", []):
        tid = int(row.get("task_id", -1))
        if tid < 0:
            continue
        out[tid] = [str(x) for x in (row.get("concept_ids") or [])]
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


def llm_rerank(
    *,
    tasks: list[dict],
    candidates_by_task: dict[int, list[TaskConceptLink]],
    llm_generator,
    batch_size: int = 10,
    max_tokens: int = 2000,
    max_retries: int = 2,
) -> tuple[list[TaskConceptLink], LLMUsage]:
    """Rerank embedding candidates via LLM, batched.

    The output preserves only the concepts that LLM picked, with a synthetic
    score equal to the original embedding score (so downstream can still rank).
    """
    settings = get_settings()
    client = llm_generator._client  # noqa: SLF001 — pragmatic reuse
    model = settings.llm_model

    out: list[TaskConceptLink] = []
    usage = LLMUsage()
    started = time.time()

    # Index candidates so we can re-attach scores after rerank
    by_id: dict[int, dict[str, TaskConceptLink]] = {}
    for tid, lst in candidates_by_task.items():
        by_id[tid] = {c.concept_id: c for c in lst}

    pending: list[tuple[dict, list[TaskConceptLink]]] = [
        (t, candidates_by_task.get(int(t["id"]), [])) for t in tasks
    ]

    total = len(pending)
    done = 0
    for start in range(0, total, batch_size):
        batch = pending[start : start + batch_size]
        payload = _build_user_payload(batch)

        last_err: Exception | None = None
        parsed: dict[int, list[str]] | None = None
        for attempt in range(max_retries + 1):
            try:
                text, resp = _call_llm(client, model, payload, max_tokens)
                parsed = _parse_response(text)
                # token bookkeeping if available
                usage.requests += 1
                u = getattr(resp, "usage", None)
                if u is not None:
                    usage.input_tokens += getattr(u, "prompt_tokens", 0) or 0
                    usage.output_tokens += getattr(u, "completion_tokens", 0) or 0
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(
                    "LLM batch %d failed (attempt %d/%d): %s",
                    start // batch_size,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                time.sleep(1.5 * (attempt + 1))
        if parsed is None:
            usage.failed += 1
            logger.error("LLM batch %d giving up after retries: %s", start // batch_size, last_err)
            # Fallback: keep top-2 embedding candidates so we don't lose the task entirely
            for task, candidates in batch:
                for c in candidates[:2]:
                    out.append(c)
            done += len(batch)
            continue

        # Materialize selected links
        for task, candidates in batch:
            tid = int(task["id"])
            picked_ids = parsed.get(tid, [])
            cand_map = by_id.get(tid, {})
            for cid in picked_ids[:3]:
                src = cand_map.get(cid)
                if src is not None:
                    out.append(src)
                else:
                    logger.debug("LLM picked unknown concept_id=%s for task=%d", cid, tid)

        done += len(batch)
        if (start // batch_size) % 10 == 0:
            logger.info("LLM rerank progress: %d/%d tasks", done, total)

    usage.elapsed_s = round(time.time() - started, 1)
    logger.info(
        "LLM rerank done: %d tasks -> %d links · %d reqs · %d in / %d out toks · %.1fs · %d failed batches",
        total,
        len(out),
        usage.requests,
        usage.input_tokens,
        usage.output_tokens,
        usage.elapsed_s,
        usage.failed,
    )
    return out, usage
