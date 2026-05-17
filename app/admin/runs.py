"""Background pipeline runs.

Each run = one subprocess invocation of ``python -m app.pipeline.strict --exam
<slug> ...``. We persist status + stdout+stderr to disk so the admin UI can
poll progress and dig into failures.

Storage layout::

    data/exams/<slug>/runs/<run_id>/
      status.json   # current state (pending / running / success / failed)
      cmd.txt       # exact argv used to launch the subprocess
      log.txt       # combined stdout + stderr stream

In-memory side: ``RunManager`` keeps the live ``asyncio.subprocess.Process``
objects so we can cancel + collect exit codes. After the process exits, the
status.json is the source of truth.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


RUN_STATUSES = ("pending", "running", "success", "failed", "cancelled")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class RunRecord:
    """Disk-shaped record stored as ``runs/{run_id}/status.json``."""

    run_id: str
    exam_slug: str
    status: str  # one of RUN_STATUSES
    started_at: str
    finished_at: str | None = None
    exit_code: int | None = None
    cmd: list[str] = field(default_factory=list)
    log_path: str = ""
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "exam_slug": self.exam_slug,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "cmd": self.cmd,
            "log_path": self.log_path,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(d["run_id"]),
            exam_slug=str(d["exam_slug"]),
            status=str(d.get("status", "pending")),
            started_at=str(d.get("started_at") or _now_iso()),
            finished_at=d.get("finished_at"),
            exit_code=d.get("exit_code"),
            cmd=list(d.get("cmd") or []),
            log_path=str(d.get("log_path", "")),
            notes=str(d.get("notes", "")),
        )


def _run_dir(exam_root: Path, run_id: str) -> Path:
    return exam_root / "runs" / run_id


def _write_status(exam_root: Path, rec: RunRecord) -> None:
    d = _run_dir(exam_root, rec.run_id)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "status.json.tmp"
    tmp.write_text(json.dumps(rec.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "status.json")


def _read_status(exam_root: Path, run_id: str) -> RunRecord | None:
    p = _run_dir(exam_root, run_id) / "status.json"
    if not p.exists():
        return None
    try:
        return RunRecord.from_json(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return None


class RunManager:
    """Single-process run scheduler. One subprocess per (exam, run_id)."""

    def __init__(self) -> None:
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(
        self,
        *,
        exam_root: Path,
        exam_slug: str,
        cmd: list[str],
        notes: str = "",
    ) -> RunRecord:
        run_id = uuid.uuid4().hex[:12]
        rd = _run_dir(exam_root, run_id)
        rd.mkdir(parents=True, exist_ok=True)
        log_path = rd / "log.txt"
        (rd / "cmd.txt").write_text(" ".join(shlex.quote(c) for c in cmd), encoding="utf-8")

        rec = RunRecord(
            run_id=run_id,
            exam_slug=exam_slug,
            status="running",
            started_at=_now_iso(),
            cmd=cmd,
            log_path=str(log_path.relative_to(exam_root)),
            notes=notes,
        )
        _write_status(exam_root, rec)

        # Open log file for combined stdout+stderr append.
        log_file = log_path.open("ab", buffering=0)

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
        except Exception as e:  # noqa: BLE001
            log_file.close()
            rec.status = "failed"
            rec.finished_at = _now_iso()
            rec.notes = f"failed to spawn: {e}"
            _write_status(exam_root, rec)
            return rec

        self._procs[run_id] = proc
        self._tasks[run_id] = asyncio.create_task(
            self._wait(run_id, proc, exam_root, log_file)
        )
        return rec

    async def _wait(
        self,
        run_id: str,
        proc: asyncio.subprocess.Process,
        exam_root: Path,
        log_file: Any,
    ) -> None:
        try:
            rc = await proc.wait()
        finally:
            try:
                log_file.close()
            except Exception:  # noqa: BLE001
                pass
        rec = _read_status(exam_root, run_id)
        if rec is None:
            return
        rec.exit_code = rc
        rec.finished_at = _now_iso()
        rec.status = "success" if rc == 0 else "failed"
        _write_status(exam_root, rec)
        # Detach
        self._procs.pop(run_id, None)
        self._tasks.pop(run_id, None)
        logger.info("Run %s for %s finished: exit=%d", run_id, rec.exam_slug, rc)

    async def cancel(self, run_id: str, exam_root: Path) -> bool:
        proc = self._procs.get(run_id)
        if proc is None:
            return False
        try:
            proc.terminate()
        except ProcessLookupError:
            return False
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        rec = _read_status(exam_root, run_id)
        if rec is not None:
            rec.status = "cancelled"
            rec.finished_at = _now_iso()
            _write_status(exam_root, rec)
        return True

    @staticmethod
    def list_runs(exam_root: Path) -> list[RunRecord]:
        runs_dir = exam_root / "runs"
        if not runs_dir.exists():
            return []
        out: list[RunRecord] = []
        for sub in sorted(runs_dir.iterdir(), reverse=True):
            if not sub.is_dir():
                continue
            p = sub / "status.json"
            if not p.exists():
                continue
            try:
                out.append(RunRecord.from_json(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001
                continue
        return out

    @staticmethod
    def get(exam_root: Path, run_id: str) -> RunRecord | None:
        return _read_status(exam_root, run_id)

    @staticmethod
    def read_log(exam_root: Path, run_id: str, tail_lines: int | None = None) -> str:
        p = _run_dir(exam_root, run_id) / "log.txt"
        if not p.exists():
            return ""
        text = p.read_text(encoding="utf-8", errors="replace")
        if tail_lines is None:
            return text
        lines = text.splitlines()
        return "\n".join(lines[-tail_lines:])
