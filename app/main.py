"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, ORJSONResponse

from app.admin.router import router as admin_router
from app.api.schemas import HealthResponse
from app.api.v1 import _health_payload, router as v1_router
from app.core.config import get_settings
from app.core.llm_budget import RateLimiter
from app.core.logging import configure_logging, get_logger
from app.deps import AppContext

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting AI Knowledge Tracing API v0.1.0")
    ctx = AppContext.startup(settings)
    app.state.ctx = ctx
    logger.info("Application ready.")
    try:
        yield
    finally:
        logger.info("Shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Knowledge Tracing",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ---- Rate limiter (per-IP, in-memory) ----
    # Protects against accidental loops / leaked URLs. Healthz and static
    # endpoints bypass the limit so monitoring stays cheap.
    settings = get_settings()
    limiter = RateLimiter(max_per_min=settings.rate_limit_per_min)
    _BYPASS = ("/healthz", "/api/v1/healthz", "/")

    @app.middleware("http")
    async def rate_limit_mw(request: Request, call_next):
        if request.url.path in _BYPASS:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Wait a minute and retry."},
            )
        return await call_next(request)

    app.include_router(v1_router)
    app.include_router(admin_router)

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz():
        ctx: AppContext = app.state.ctx
        return _health_payload(ctx)

    @app.get("/")
    async def root():
        return {
            "name": "AI Knowledge Tracing",
            "version": "0.1.0",
            "endpoints": [
                "GET  /healthz",
                "GET  /api/v1/exams",
                "GET  /api/v1/exams/{slug}/bank",
                "POST /api/v1/exams/{slug}/explain",
                "POST /api/v1/exams/{slug}/event",
                "POST /api/v1/exams/{slug}/recommend",
                "GET  /api/v1/exams/{slug}/mastery/{user_id}",
                "GET  /api/v1/exams/{slug}/viewer",
                "POST /api/v1/admin/exams",
                "POST /api/v1/admin/exams/{slug}/bank (multipart)",
                "POST /api/v1/admin/exams/{slug}/theory (multipart)",
                "POST /api/v1/admin/exams/{slug}/ingest",
                "GET  /api/v1/admin/exams/{slug}/runs",
            ],
        }

    return app


app = create_app()
