"""API v1 router."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.api.schemas import (
    BudgetSnapshot,
    ConceptUpdateOut,
    DueConcept,
    EventRequest,
    EventResponse,
    ExamGraphHealth,
    ExamListItem,
    ExamListResponse,
    ExamStats,
    ExplainRequest,
    ExplainResponse,
    GraphSummaryResponse,
    HealthResponse,
    MasteryResponse,
    RecommendItem,
    RecommendRequest,
    RecommendResponse,
    ThemeArticleResponse,
    ThemeArticleSection,
    ThemeConcept,
)
from app.core.llm_budget import get_budget
from app.core.logging import get_logger
from app.deps import (
    AppContext,
    get_ctx,
    get_exams,
    get_graphs,
)
from app.exams.bkt import MasteryRepository, aggregate_mastery
from app.exams.graph_service import GraphRegistry
from app.exams.registry import Exam, ExamRegistry, UnknownExamError, load_bank
from app.services.bank_explain import UnknownBankTaskError, explain_bank_task
from app.services.events import EventInput, UnknownTaskError, record_event
from app.services.recommend import recommend_next
from app.services.theme_summary import generate_summary
from app.services.viewer import render_viewer_html

router = APIRouter(prefix="/api/v1")
logger = get_logger(__name__)


# ============================================================
# /exams — multi-exam trainer plane
# ============================================================


@router.get("/exams", response_model=ExamListResponse)
async def list_exams(exams: ExamRegistry = Depends(get_exams)):
    items: list[ExamListItem] = []
    for exam in exams.published():
        if not exam.bank_path.exists():
            # Published but bank missing — skip in trainer plane; admin still sees it.
            continue
        bank = load_bank(exam)
        items.append(
            ExamListItem(
                slug=exam.slug,
                title=exam.title,
                subtitle=exam.subtitle,
                version=exam.version,
                published=exam.published,
                stats=ExamStats(**(bank.get("_meta", {}).get("stats", {}))),
            )
        )
    return ExamListResponse(exams=items)


def _get_exam_or_404(exams: ExamRegistry, slug: str):
    try:
        return exams.get(slug)
    except UnknownExamError:
        raise HTTPException(status_code=404, detail=f"Unknown exam: {slug}") from None


@router.get("/exams/{slug}/bank")
async def get_exam_bank(slug: str, exams: ExamRegistry = Depends(get_exams)):
    exam = _get_exam_or_404(exams, slug)
    if not exam.bank_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Bank not uploaded for {slug}"
        )
    return load_bank(exam)


@router.post("/exams/{slug}/explain", response_model=ExplainResponse)
async def explain_exam_task(
    slug: str,
    payload: ExplainRequest,
    exams: ExamRegistry = Depends(get_exams),
    ctx: AppContext = Depends(get_ctx),
):
    exam = _get_exam_or_404(exams, slug)
    try:
        return explain_bank_task(
            exam=exam,
            task_id=payload.task_id,
            picked_label=payload.picked_label,
            embedder=ctx.embedder,
            store=ctx.store,
            llm_generator=ctx.generator,
        )
    except UnknownBankTaskError as e:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {e}") from None
    except Exception as e:  # noqa: BLE001
        logger.exception("explain failed: %s", e)
        raise HTTPException(
            status_code=502, detail=f"explain failed: {type(e).__name__}: {e}"
        ) from None


def _mastery_repo(exam: Exam) -> MasteryRepository:
    return MasteryRepository(exam_root=exam.root, exam_slug=exam.slug)


@router.post("/exams/{slug}/event", response_model=EventResponse)
async def record_exam_event(
    slug: str,
    payload: EventRequest,
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
):
    exam = _get_exam_or_404(exams, slug)
    graph = graphs.get(exam)
    log_path = exam.root / "events.jsonl"
    try:
        result = record_event(
            graph=graph,
            repo=_mastery_repo(exam),
            event=EventInput(
                user_id=payload.user_id,
                task_id=payload.task_id,
                picked_label=payload.picked_label,
                is_correct=payload.is_correct,
                ts=payload.ts,
            ),
            log_path=log_path,
        )
    except UnknownTaskError as e:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {e}") from None
    return EventResponse(
        user_id=result.user_id,
        task_id=result.task_id,
        is_correct=result.is_correct,
        overall_mastery=result.overall_mastery,
        updates=[
            ConceptUpdateOut(
                concept_id=u.concept_id,
                concept_term=u.concept_term,
                p_before=u.p_before,
                p_after=u.p_after,
                weight=u.weight,
            )
            for u in result.updates
        ],
    )


@router.post("/exams/{slug}/recommend", response_model=RecommendResponse)
async def recommend_exam_tasks(
    slug: str,
    payload: RecommendRequest,
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
):
    exam = _get_exam_or_404(exams, slug)
    graph = graphs.get(exam)
    repo = _mastery_repo(exam)
    store = repo.load(payload.user_id)
    log_path = exam.root / "events.jsonl"
    items = recommend_next(
        graph=graph,
        store=store,
        count=payload.count,
        log_path=log_path,
        target_p=payload.target_p,
    )
    return RecommendResponse(
        user_id=payload.user_id,
        target_p=payload.target_p,
        items=[
            RecommendItem(
                task_id=r.task_id,
                score=r.score,
                expected_p_correct=r.expected_p_correct,
                reason=r.reason,
                target_concepts=r.target_concepts,
                due_score=r.due_score,
            )
            for r in items
        ],
    )


@router.get("/exams/{slug}/theme/{code}", response_model=ThemeArticleResponse)
async def get_theme_article(
    slug: str,
    code: str,
    raw: bool = False,
    task_ids: str | None = None,
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
    ctx: AppContext = Depends(get_ctx),
):
    """Return a theory article for one theme.

    Default: returns LLM-clean ``summary_md`` (~250 words, no page artifacts).
    With ``?raw=1``: returns raw MD sections from ``theme_sections.json``
    (useful for debugging the linker output).
    With ``?task_ids=1,2,3``: grounds the summary on EXACTLY these tasks (the
    ones the student is about to see in a lesson), so the theory prepares them
    for those specific questions rather than the theme in general.
    """
    exam = _get_exam_or_404(exams, slug)
    bank = load_bank(exam)
    theme = next((t for t in bank.get("themes", []) if str(t.get("code")) == str(code)), None)
    if not theme:
        raise HTTPException(status_code=404, detail=f"Unknown theme: {code}")
    chapter = next(
        (c for c in bank.get("chapters", []) if int(c.get("id") or 0) == int(theme.get("chapter_id") or 0)),
        None,
    )

    ts_path = exam.root / "theme_sections.json"
    if not ts_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"theme_sections.json not built for {slug}. Run pipeline with "
                "--link-theory first."
            ),
        )
    import json as _json
    data = _json.loads(ts_path.read_text(encoding="utf-8"))
    sections_raw = (data.get("by_theme") or {}).get(str(code), [])

    # Materialise excerpts from theory.md when possible (offsets are exact).
    theory_text: str | None = None
    if exam.theory_path and exam.theory_path.exists():
        try:
            theory_text = exam.theory_path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            theory_text = None

    sections: list[ThemeArticleSection] = []
    for s in sections_raw:
        off = int(s.get("char_offset", 0) or 0)
        n = int(s.get("char_length", 0) or 0)
        excerpt = ""
        if theory_text and n > 0:
            excerpt = theory_text[off : off + n]
        sections.append(
            ThemeArticleSection(
                chunk_id=str(s.get("chunk_id", "")),
                section_path=str(s.get("section_path", "")),
                snippet=str(s.get("snippet", "")),
                score=float(s.get("score") or 0.0),
                char_offset=off,
                char_length=n,
                excerpt=excerpt,
            )
        )

    # --- Theme's actual tasks + the concepts they test (the grounding signal) ---
    graph = graphs.get(exam)
    theme_tasks = [t for t in bank.get("tasks", []) if str(t.get("theme_code")) == str(code)]
    task_count = len(theme_tasks)

    # Optional focus: ground on EXACTLY the tasks the lesson will show.
    focus_ids: list[int] = []
    if task_ids:
        for part in task_ids.split(","):
            part = part.strip()
            if part.isdigit():
                focus_ids.append(int(part))
    cache_variant: str | None = None
    if focus_ids:
        by_id = {int(t["id"]): t for t in theme_tasks if t.get("id") is not None}
        focus_tasks = [by_id[i] for i in focus_ids if i in by_id]
        if focus_tasks:
            theme_tasks = focus_tasks  # narrows ranking + sample to the shown tasks
            cache_variant = hashlib.sha1(
                ",".join(str(i) for i in focus_ids).encode()
            ).hexdigest()[:10]

    grounding_ids = [int(t["id"]) for t in theme_tasks if t.get("id") is not None]

    # Concepts ranked by how strongly THESE tasks test them (TESTS_CONCEPT).
    # Falls back to BELONGS_TO_THEME when task links are absent so the block is
    # never empty for a populated theme.
    ranked_concept_ids = graph.tested_concepts_for_tasks(grounding_ids, top_k=30)
    if not ranked_concept_ids:
        ranked_concept_ids = graph.concepts_by_theme.get(str(code), [])[:30]

    concepts_out: list[ThemeConcept] = []
    for cid in ranked_concept_ids:
        info = graph.concept_info.get(cid) or {}
        concepts_out.append(
            ThemeConcept(
                id=cid,
                term=str(info.get("term") or cid),
                definition=str(info.get("definition") or "")[:400],
                prereq_count=len(graph.prereqs_of.get(cid, [])),
            )
        )

    # A small sample of the real questions, to steer the summary toward exactly
    # what the exam asks in this theme.
    def _correct_text(t: dict) -> str:
        for o in t.get("options") or []:
            if o.get("is_correct"):
                return str(o.get("text") or "")
        return str(t.get("solution_text") or "")

    task_sample = [
        {"task_text": str(t.get("task_text") or ""), "correct": _correct_text(t)}
        for t in theme_tasks[:6]
    ]
    concept_sample = [
        {"term": c.term, "definition": c.definition} for c in concepts_out[:6]
    ]

    # LLM-clean summary, grounded on the theme's tasks + tested concepts (cached).
    # Generated lazily on first request; <1s on cache hit.
    summary_md: str | None = None
    cached = False
    if not raw:
        try:
            section_dicts = [
                {
                    "section_path": s.section_path,
                    "snippet": s.snippet,
                    "excerpt": s.excerpt,
                }
                for s in sections[:5]
            ]
            res = generate_summary(
                exam=exam,
                theme_code=str(code),
                theme_name=str(theme.get("name") or code),
                chapter_name=(chapter or {}).get("name"),
                sections=section_dicts,
                llm_generator=ctx.generator,
                tasks=task_sample,
                concepts=concept_sample,
                variant=cache_variant,
            )
            summary_md = res.summary_md
            cached = res.cached
        except Exception as e:  # noqa: BLE001
            logger.warning("Theme summary failed for %s/%s: %s", slug, code, e)

    return ThemeArticleResponse(
        slug=slug,
        theme_code=str(code),
        theme_name=str(theme.get("name") or code),
        chapter_name=(chapter or {}).get("name"),
        chapter_num=int(chapter.get("num") or 0) if chapter else None,
        sections=sections,
        summary_md=summary_md,
        summary_cached=cached,
        concepts=concepts_out,
        task_count=task_count,
    )


@router.get("/exams/{slug}/viewer", response_class=HTMLResponse)
async def exam_viewer(
    slug: str,
    layout: str = "tree",
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
):
    """Render the graph viewer.

    Default ``layout=tree`` shows our hierarchical Chapter → Theme → Task
    explorer. ``layout=cytoscape`` falls back to the vendored k2-18 tabular
    viewer (kept for completeness, but flat 2700-node list is hard to use).
    """
    exam = _get_exam_or_404(exams, slug)
    g = graphs.get(exam)
    if not g.nodes:
        raise HTTPException(
            status_code=503,
            detail=f"Strict graph for {slug} not built yet — run app.pipeline.strict first",
        )
    try:
        html = render_viewer_html(exam, g, layout=layout)
    except Exception as e:  # noqa: BLE001
        logger.exception("Viewer render failed: %s", e)
        raise HTTPException(
            status_code=500, detail=f"viewer render failed: {type(e).__name__}: {e}"
        ) from None
    return HTMLResponse(content=html, status_code=200)


@router.get("/exams/{slug}/graph/summary", response_model=GraphSummaryResponse)
async def graph_summary(
    slug: str,
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
):
    exam = _get_exam_or_404(exams, slug)
    g = graphs.get(exam)
    stats = (g.meta or {}).get("stats", {})
    sample_concepts = [
        {"id": cid, "term": info.get("term"), "definition": (info.get("definition") or "")[:200]}
        for cid, info in list(g.concept_info.items())[:5]
    ]
    sample_links: list[dict] = []
    for task_id, skills in list(g.skills_by_task.items())[:5]:
        sample_links.append(
            {
                "task_id": task_id,
                "concepts": [
                    {"id": s.concept_id, "term": s.concept_term, "score": s.score}
                    for s in skills[:3]
                ],
            }
        )
    return GraphSummaryResponse(
        slug=exam.slug,
        title=exam.title,
        pipeline_mode=str((g.meta or {}).get("pipeline_mode", "strict")),
        version=str((g.meta or {}).get("version", "")),
        nodes=int(stats.get("nodes", 0)),
        edges=int(stats.get("edges", 0)),
        by_node_type=dict(stats.get("by_node_type", {})),
        by_edge_type=dict(stats.get("by_edge_type", {})),
        linked_concepts=int(stats.get("linked_concepts", 0)),
        sample_concepts=sample_concepts,
        sample_links=sample_links,
    )


@router.get("/exams/{slug}/mastery/{user_id}", response_model=MasteryResponse)
async def get_user_mastery(
    slug: str,
    user_id: int,
    exams: ExamRegistry = Depends(get_exams),
    graphs: GraphRegistry = Depends(get_graphs),
):
    import time as _time
    from datetime import datetime, timezone

    exam = _get_exam_or_404(exams, slug)
    graph = graphs.get(exam)
    store = _mastery_repo(exam).load(user_id)
    agg = aggregate_mastery(
        store=store,
        concepts_by_theme=graph.concepts_by_theme,
        themes_by_chapter=graph.themes_by_chapter,
    )

    # FSRS due concepts: those previously reviewed whose retrievability has
    # dropped below the target. Return top-10 by lowest retrievability.
    now = _time.time()
    due: list[DueConcept] = []
    for cid, ts in store.last_seen.items():
        r = store.retrievability_for(cid, now)
        if r >= 0.92:
            continue
        info = graph.concept_info.get(cid) or {}
        due.append(
            DueConcept(
                concept_id=cid,
                term=str(info.get("term") or cid),
                p_l=round(store.p_l(cid), 4),
                retrievability=round(r, 4),
                last_seen_iso=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            )
        )
    due.sort(key=lambda d: d.retrievability)

    return MasteryResponse(
        user_id=user_id,
        exam_slug=exam.slug,
        events=store.events,
        overall=agg.overall,
        by_concept={k: round(v, 4) for k, v in agg.by_concept.items()},
        by_theme={k: round(v, 4) for k, v in agg.by_theme.items()},
        by_chapter={str(k): round(v, 4) for k, v in agg.by_chapter.items()},
        due_concepts=due[:10],
    )


# Healthcheck (mounted by main.py at /healthz too)
@router.get("/healthz", response_model=HealthResponse)
async def healthz_v1(ctx: AppContext = Depends(get_ctx)):
    return _health_payload(ctx)


def _health_payload(ctx: AppContext) -> HealthResponse:
    from app.rag.vectorstore import ALL_COLLECTIONS

    vs_ready = all(ctx.store.count(c) > 0 for c in ALL_COLLECTIONS)
    exam_blocks: list[ExamGraphHealth] = []
    any_graph = False
    for exam in ctx.exams.published():
        try:
            g = ctx.graphs.get(exam)
        except Exception:  # noqa: BLE001
            continue
        stats = (g.meta or {}).get("stats", {})
        nbt = stats.get("by_node_type", {})
        ebt = stats.get("by_edge_type", {})
        if stats.get("nodes"):
            any_graph = True
        exam_blocks.append(
            ExamGraphHealth(
                slug=exam.slug,
                title=exam.title,
                nodes=int(stats.get("nodes", 0)),
                edges=int(stats.get("edges", 0)),
                chapters=int(nbt.get("Chapter", 0)),
                themes=int(nbt.get("Theme", 0)),
                tasks=int(nbt.get("Task", 0)),
                concepts=int(nbt.get("Concept", 0)),
                task_concept_links=int(ebt.get("TESTS_CONCEPT", 0)),
                prereq_edges=int(ebt.get("PREREQUISITE", 0)),
            )
        )
    return HealthResponse(
        status="ok" if (ctx.ready and vs_ready and any_graph) else "degraded",
        graph_loaded=any_graph,
        vector_store_ready=vs_ready,
        llm_configured=bool(ctx.settings.effective_api_key),
        exams=exam_blocks,
        budget=BudgetSnapshot(**get_budget().snapshot()),
    )
