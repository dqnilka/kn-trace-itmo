"""Pydantic schemas for API requests / responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# Common
# ============================================================


class Source(BaseModel):
    """A single piece of evidence used to compose theory_content."""

    node_id: str = Field(..., description="ID of the source node (graph chunk/concept) or md chunk id.")
    node_type: Literal["Chunk", "Concept", "Assessment", "MdChunk"] = Field(
        ..., description="Type of the source."
    )
    score: float = Field(..., description="Combined relevance score (graph weight * vector similarity).")
    snippet: str = Field(..., description="Short excerpt of the source text (truncated).")


class ExamGraphHealth(BaseModel):
    """Per-exam strict-graph snapshot for HealthBadge."""

    slug: str
    title: str
    nodes: int
    edges: int
    chapters: int
    themes: int
    tasks: int
    concepts: int
    task_concept_links: int
    prereq_edges: int = 0


class BudgetSnapshot(BaseModel):
    """LLM spend so far this process. Cheap to compute; not persisted."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cached_hits: int = 0
    uptime_seconds: int = 0


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    graph_loaded: bool
    vector_store_ready: bool
    llm_configured: bool
    # Strict per-exam graphs — the source of truth.
    exams: list[ExamGraphHealth] = Field(default_factory=list)
    # LLM budget meter (resets on process restart).
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)


# ============================================================
# /admin/* (no auth in MVP)
# ============================================================


class AdminExamCreateRequest(BaseModel):
    slug: str = Field(..., description="URL-safe slug, [A-Za-z0-9_-]+", min_length=1)
    title: str = Field(..., min_length=1)
    subtitle: str = ""
    theory_path: str | None = None


class AdminExamCreateResponse(BaseModel):
    slug: str
    title: str
    published: bool


class AdminBankUploadResponse(BaseModel):
    slug: str
    bank_path: str
    size_bytes: int
    stats: dict[str, int] = Field(default_factory=dict)


class AdminTheoryUploadResponse(BaseModel):
    slug: str
    theory_path: str
    size_bytes: int


class AdminIngestRequest(BaseModel):
    top_k: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.35, ge=0.0, le=1.0)
    limit: int = Field(default=0, ge=0, description="0 = process all tasks")
    llm_rerank: bool = Field(default=False)
    llm_top_k: int = Field(default=8, ge=1, le=20)
    llm_batch: int = Field(default=8, ge=1, le=32)


class AdminRunRecord(BaseModel):
    run_id: str
    exam_slug: str
    status: Literal["pending", "running", "success", "failed", "cancelled"]
    started_at: str
    finished_at: str | None = None
    exit_code: int | None = None
    cmd: list[str] = Field(default_factory=list)
    log_path: str = ""
    notes: str = ""


class ThemeArticleSection(BaseModel):
    chunk_id: str
    section_path: str = ""
    snippet: str = ""
    score: float = 0.0
    char_offset: int = 0
    char_length: int = 0
    excerpt: str = ""  # full text of the section, if available


class ThemeConcept(BaseModel):
    id: str
    term: str
    definition: str = ""
    prereq_count: int = 0


class ThemeArticleResponse(BaseModel):
    slug: str
    theme_code: str
    theme_name: str
    chapter_name: str | None = None
    chapter_num: int | None = None
    sections: list[ThemeArticleSection] = Field(default_factory=list)
    summary_md: str | None = None
    summary_cached: bool = False
    concepts: list[ThemeConcept] = Field(default_factory=list)
    task_count: int = 0


class GraphSummaryResponse(BaseModel):
    slug: str
    title: str
    pipeline_mode: str
    version: str
    nodes: int
    edges: int
    by_node_type: dict[str, int]
    by_edge_type: dict[str, int]
    linked_concepts: int
    sample_concepts: list[dict] = Field(default_factory=list)
    sample_links: list[dict] = Field(default_factory=list)


# ============================================================
# /exams (multi-exam trainer plane)
# ============================================================


class ExamStats(BaseModel):
    chapters: int = 0
    themes: int = 0
    tasks: int = 0
    options: int = 0


class ExamListItem(BaseModel):
    slug: str
    title: str
    subtitle: str = ""
    version: str = "0.0.0"
    published: bool = True
    stats: ExamStats = Field(default_factory=ExamStats)


class ExamListResponse(BaseModel):
    exams: list[ExamListItem]


class ExplainRequest(BaseModel):
    task_id: int = Field(..., description="Bank task id from this exam's bank.json")
    picked_label: str | None = Field(
        default=None, description="Label the user picked (e.g. '2'); None for skipped."
    )


class ExplainResponse(BaseModel):
    task_id: int
    theme_code: str
    chapter_name: str | None = None
    theme_name: str | None = None
    correct_label: str
    picked_label: str | None = None
    is_correct: bool
    explanation_md: str
    sources: list[Source] = Field(default_factory=list)
    generation_mode: Literal["llm", "extractive"] = "llm"


# ============================================================
# /event — record answer + BKT update
# ============================================================


class EventRequest(BaseModel):
    user_id: int
    task_id: int
    picked_label: str | None = None
    is_correct: bool
    ts: float | None = None


class ConceptUpdateOut(BaseModel):
    concept_id: str
    concept_term: str
    p_before: float
    p_after: float
    weight: float


class EventResponse(BaseModel):
    user_id: int
    task_id: int
    is_correct: bool
    updates: list[ConceptUpdateOut]
    overall_mastery: float | None = None


# ============================================================
# /recommend — adaptive next-item picker
# ============================================================


class RecommendRequest(BaseModel):
    user_id: int
    count: int = Field(default=5, ge=1, le=20)
    target_p: float = Field(default=0.65, ge=0.05, le=0.95)


class RecommendItem(BaseModel):
    task_id: int
    score: float
    expected_p_correct: float
    reason: str
    target_concepts: list[tuple[str, str, float]] = Field(default_factory=list)
    due_score: float = 0.0


class RecommendResponse(BaseModel):
    user_id: int
    target_p: float
    items: list[RecommendItem]


# ============================================================
# /mastery — server-side knowledge state
# ============================================================


class DueConcept(BaseModel):
    concept_id: str
    term: str
    p_l: float
    retrievability: float
    last_seen_iso: str | None = None


class MasteryResponse(BaseModel):
    user_id: int
    exam_slug: str
    events: int
    overall: float | None
    by_concept: dict[str, float]
    by_theme: dict[str, float]
    by_chapter: dict[str, float]  # keys as strings for JSON compat
    due_concepts: list[DueConcept] = Field(default_factory=list)
