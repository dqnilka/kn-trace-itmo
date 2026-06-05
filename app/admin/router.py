"""Admin API endpoints (no auth in MVP).

Routes under ``/api/v1/admin/exams/...``. Manages exam manifests, uploads
artifacts, kicks off pipeline runs, toggles publish state.

Auth: deliberately none right now. The user (product owner) decided "не
концентрируйся на auth и прочем - это все можно докрутить потом". Add a
gate when going to multi-user / prod.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.admin.runs import RunManager, RunRecord
from app.api.schemas import (
    AdminBankUploadResponse,
    AdminExamCreateRequest,
    AdminExamCreateResponse,
    AdminIngestRequest,
    AdminRunRecord,
    AdminTheoryUploadResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.deps import AppContext, get_ctx, get_exams
from app.exams.registry import (
    Exam,
    ExamRegistry,
    UnknownExamError,
    load_exam,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---------- helpers ----------


def _settings_exams_dir() -> Path:
    return Path(get_settings().exams_dir)


def _exam_root(slug: str) -> Path:
    return _settings_exams_dir() / slug


def _write_manifest(slug: str, data: dict[str, Any]) -> None:
    p = _exam_root(slug) / "exam.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_manifest(slug: str) -> dict[str, Any]:
    p = _exam_root(slug) / "exam.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}")
    return json.loads(p.read_text(encoding="utf-8"))


def _get_exam(exams: ExamRegistry, slug: str) -> Exam:
    try:
        return exams.get(slug)
    except UnknownExamError:
        # Try refresh — maybe just created.
        exams.reload()
        try:
            return exams.get(slug)
        except UnknownExamError:
            raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}") from None


# ---------- CRUD: exams ----------


@router.get("/exams")
async def list_exams_admin(exams: ExamRegistry = Depends(get_exams)):
    """Admin list — includes unpublished/draft exams."""
    # Re-scan so we see manifests created via filesystem.
    exams.reload()
    result = []
    for e in exams.all():
        m = e.raw_manifest or {}
        result.append(
            {
                "slug": e.slug,
                "title": e.title,
                "subtitle": e.subtitle,
                "version": e.version,
                "published": e.published,
                "has_bank": e.bank_path.exists(),
                "has_theory": e.has_theory,
                "root": str(e.root),
                "manifest": m,
            }
        )
    return {"exams": result}


@router.post("/exams", response_model=AdminExamCreateResponse, status_code=201)
async def create_exam(
    payload: AdminExamCreateRequest,
    exams: ExamRegistry = Depends(get_exams),
):
    slug = payload.slug.strip()
    if not slug or not all(c.isalnum() or c in "-_" for c in slug):
        raise HTTPException(status_code=400, detail="slug must match [A-Za-z0-9_-]+")
    target = _exam_root(slug)
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Exam already exists: {slug}")
    target.mkdir(parents=True, exist_ok=False)
    manifest = {
        "slug": slug,
        "title": payload.title.strip() or slug,
        "subtitle": payload.subtitle or "",
        "version": "0.1.0",
        "published": False,
        "bank_path": "bank.json",
        "theory_path": payload.theory_path or None,
        "rag": {
            "collections": ["md_chunks", "graph_chunks"],
            "top_k": 6,
        },
    }
    _write_manifest(slug, manifest)
    exams.reload()
    return AdminExamCreateResponse(slug=slug, title=manifest["title"], published=False)


@router.delete("/exams/{slug}")
async def delete_exam(slug: str, exams: ExamRegistry = Depends(get_exams)):
    root = _exam_root(slug)
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}")
    shutil.rmtree(root, ignore_errors=True)
    exams.reload()
    return {"ok": True, "slug": slug}


@router.post("/exams/{slug}/publish")
async def publish_exam(slug: str, exams: ExamRegistry = Depends(get_exams)):
    m = _read_manifest(slug)
    m["published"] = True
    _write_manifest(slug, m)
    exams.reload()
    return {"ok": True, "slug": slug, "published": True}


@router.post("/exams/{slug}/unpublish")
async def unpublish_exam(slug: str, exams: ExamRegistry = Depends(get_exams)):
    m = _read_manifest(slug)
    m["published"] = False
    _write_manifest(slug, m)
    exams.reload()
    return {"ok": True, "slug": slug, "published": False}


# ---------- uploads ----------


@router.post("/exams/{slug}/bank", response_model=AdminBankUploadResponse)
async def upload_bank(
    slug: str,
    file: UploadFile = File(...),
    exams: ExamRegistry = Depends(get_exams),
):
    """Upload a bank XLSX, run convert_bank.py to produce bank.json.

    The XLSX itself is kept under ``sources/`` for audit.
    """
    if not _exam_root(slug).exists():
        raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Expected .xlsx file")

    src_dir = _exam_root(slug) / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = src_dir / "bank.xlsx"
    with xlsx_path.open("wb") as f:
        data = await file.read()
        f.write(data)

    bank_path = _exam_root(slug) / "bank.json"
    # Run convert_bank.py inline (fast, <5s).
    from scripts import convert_bank  # imported lazily so test harness can stub
    meta = convert_bank.convert(xlsx_path, bank_path)
    exams.reload()
    return AdminBankUploadResponse(
        slug=slug,
        bank_path=str(bank_path),
        size_bytes=bank_path.stat().st_size,
        stats=meta.get("stats", {}),
    )


@router.post("/exams/{slug}/theory", response_model=AdminTheoryUploadResponse)
async def upload_theory(
    slug: str,
    file: UploadFile = File(...),
    exams: ExamRegistry = Depends(get_exams),
):
    """Upload theory.md (raw markdown)."""
    root = _exam_root(slug)
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}")
    if not file.filename or not file.filename.lower().endswith((".md", ".markdown")):
        raise HTTPException(status_code=400, detail="Expected .md file")
    target = root / "theory.md"
    data = await file.read()
    target.write_bytes(data)

    # Update manifest to point at the new theory file.
    m = _read_manifest(slug)
    m["theory_path"] = "theory.md"
    _write_manifest(slug, m)
    exams.reload()
    return AdminTheoryUploadResponse(
        slug=slug,
        theory_path=str(target),
        size_bytes=target.stat().st_size,
    )


# ---------- ingest runs ----------


def _build_pipeline_cmd(slug: str, args: AdminIngestRequest) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        "-m",
        "app.pipeline.strict",
        "--exam",
        slug,
        "--top-k",
        str(args.top_k),
        "--min-score",
        str(args.min_score),
    ]
    if args.limit and args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    if args.llm_rerank:
        cmd += [
            "--llm-rerank",
            "--llm-top-k",
            str(args.llm_top_k),
            "--llm-batch",
            str(args.llm_batch),
        ]
    return cmd


@router.post("/exams/{slug}/ingest")
async def start_ingest(
    slug: str,
    payload: AdminIngestRequest,
    exams: ExamRegistry = Depends(get_exams),
    ctx: AppContext = Depends(get_ctx),
):
    exam = _get_exam(exams, slug)
    if not exam.bank_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Bank not uploaded yet — POST /admin/exams/{slug}/bank first",
        )
    cmd = _build_pipeline_cmd(slug, payload)
    rec = await ctx.runs.start(
        exam_root=exam.root,
        exam_slug=slug,
        cmd=cmd,
        notes=("llm-rerank" if payload.llm_rerank else "embeddings-only"),
    )
    return rec.to_json()


@router.get("/exams/{slug}/runs")
async def list_runs(slug: str, exams: ExamRegistry = Depends(get_exams)):
    exam = _get_exam(exams, slug)
    runs = RunManager.list_runs(exam.root)
    return {"runs": [r.to_json() for r in runs]}


@router.get("/exams/{slug}/runs/{run_id}")
async def get_run(
    slug: str,
    run_id: str,
    exams: ExamRegistry = Depends(get_exams),
):
    exam = _get_exam(exams, slug)
    rec = RunManager.get(exam.root, run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return rec.to_json()


@router.get("/exams/{slug}/runs/{run_id}/log")
async def get_run_log(
    slug: str,
    run_id: str,
    tail: int = 500,
    exams: ExamRegistry = Depends(get_exams),
):
    exam = _get_exam(exams, slug)
    log = RunManager.read_log(exam.root, run_id, tail_lines=tail)
    return {"run_id": run_id, "log": log}


@router.post("/exams/{slug}/runs/{run_id}/cancel")
async def cancel_run(
    slug: str,
    run_id: str,
    exams: ExamRegistry = Depends(get_exams),
    ctx: AppContext = Depends(get_ctx),
):
    exam = _get_exam(exams, slug)
    ok = await ctx.runs.cancel(run_id, exam.root)
    if not ok:
        raise HTTPException(status_code=404, detail="No live process for this run_id")
    return {"ok": True}


# ---------- reload ----------


@router.post("/reload")
async def reload_registry(
    exams: ExamRegistry = Depends(get_exams),
    ctx: AppContext = Depends(get_ctx),
):
    """Force-reload exam manifests AND strict-graph cache.

    Use after manually editing files on disk or after an ingest run completes.
    """
    exams.reload()
    ctx.graphs._cache.clear()  # noqa: SLF001 — internal cache invalidation
    # Eager preload
    for e in exams.published():
        try:
            ctx.graphs.get(e)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "exams": [e.slug for e in exams.all()]}


@router.get("/feedback")
async def feedback_summary(
    exams: ExamRegistry = Depends(get_exams),
):
    """Аналитика оценок (лайки/дизлайки теории и занятий) для админки.

    Возвращает: тоталы по kind+rating, разбивку по темам (с названиями) и
    последние комментарии к дизлайкам.
    """
    from app.core.db import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetch(
            "SELECT kind, rating, COUNT(*) AS n FROM feedback GROUP BY kind, rating"
        )
        by_theme = await conn.fetch(
            """SELECT ref,
                      COUNT(*) FILTER (WHERE rating='like')    AS likes,
                      COUNT(*) FILTER (WHERE rating='dislike') AS dislikes
               FROM feedback WHERE kind='theory' AND ref <> ''
               GROUP BY ref ORDER BY dislikes DESC, likes DESC LIMIT 100"""
        )
        comments = await conn.fetch(
            """SELECT kind, ref, comment, created_at FROM feedback
               WHERE rating='dislike' AND comment IS NOT NULL AND comment <> ''
               ORDER BY created_at DESC LIMIT 100"""
        )

    # Названия тем по коду — из банка опубликованного экзамена.
    names: dict[str, str] = {}
    try:
        from app.exams.registry import load_bank

        for e in exams.all():
            bank = load_bank(e)
            for t in bank.get("themes", []):
                names[str(t.get("code"))] = str(t.get("name") or t.get("code"))
    except Exception:  # noqa: BLE001
        pass

    return {
        "totals": [dict(r) for r in totals],
        "by_theme": [
            {
                "ref": r["ref"],
                "theme_name": names.get(r["ref"], r["ref"]),
                "likes": r["likes"],
                "dislikes": r["dislikes"],
            }
            for r in by_theme
        ],
        "comments": [
            {
                "kind": r["kind"],
                "ref": r["ref"],
                "theme_name": names.get(r["ref"], r["ref"]),
                "comment": r["comment"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in comments
        ],
    }
