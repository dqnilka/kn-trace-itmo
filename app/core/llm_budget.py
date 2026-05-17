"""LLM cost guard: disk-cache + token counter + simple rate limiter.

Three layers of protection against runaway spend:

  1. **Cache** — deterministic LLM calls (bank_explain per task_id/picked_label,
     theme_summary per content-hash) hit disk first. After first generation
     same input → instant zero-cost response.

  2. **Budget meter** — in-memory counter of input/output tokens accumulated
     since process start. Exposed via ``/healthz`` so operators can see spend
     without scraping logs.

  3. **Rate limit** — IP-keyed token-bucket on the FastAPI middleware. Default
     30 req/min/IP is enough for one student clicking through a session but
     blocks accidental loops.

All three are no-ops when the corresponding setting is disabled.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------
# 1. Disk cache for LLM responses
# ----------------------------------------------------------------


def cache_key(provider: str, model: str, parts: list[Any]) -> str:
    """Stable hash for a (provider, model, prompt-parts) tuple."""
    h = hashlib.sha256()
    h.update(provider.encode())
    h.update(b"|")
    h.update(model.encode())
    h.update(b"|")
    for p in parts:
        h.update(b"\x00")
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:32]


def cache_path(root: Path, key: str) -> Path:
    return root / key[:2] / f"{key}.json"


def cache_get(root: Path, key: str) -> dict | None:
    p = cache_path(root, key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def cache_put(root: Path, key: str, payload: dict) -> None:
    p = cache_path(root, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ----------------------------------------------------------------
# 2. Budget meter (in-memory, cheap)
# ----------------------------------------------------------------


class BudgetMeter:
    """Accumulates input/output tokens across all LLM calls in the process.

    Threadsafe via a simple lock. The numbers reset on each process restart;
    for cross-restart accounting, persist via a separate sidecar (out of MVP
    scope).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._input_tokens = 0
        self._output_tokens = 0
        self._calls = 0
        self._cached_hits = 0
        self._started_at = time.time()

    def record(self, *, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self._input_tokens += int(input_tokens)
            self._output_tokens += int(output_tokens)
            self._calls += 1

    def record_cache_hit(self) -> None:
        with self._lock:
            self._cached_hits += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "calls": self._calls,
                "cached_hits": self._cached_hits,
                "uptime_seconds": int(time.time() - self._started_at),
            }


_BUDGET = BudgetMeter()


def get_budget() -> BudgetMeter:
    return _BUDGET


# ----------------------------------------------------------------
# 3. Rate limiter (IP keyed, sliding window, 60s)
# ----------------------------------------------------------------


class RateLimiter:
    """Sliding-window rate limiter per IP. In-memory, single-process.

    For multi-instance deployments, swap to Redis. For our MVP single-container
    deployment this is sufficient and zero-dep.
    """

    def __init__(self, max_per_min: int) -> None:
        self._max = max_per_min
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self._max <= 0:
            return True
        now = time.time()
        cutoff = now - 60.0
        with self._lock:
            q = self._windows[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True


def truncate_for_budget(text: str, max_chars: int) -> str:
    """Hard-cap input text to avoid runaway prompt sizes."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = text[: max_chars - 200]
    return head + "\n\n[…усечено для контроля бюджета токенов]"
