"""PostgreSQL access layer (asyncpg pool + schema bootstrap).

Used by the auth layer (users) and server-side progress (user_mastery). The
DB lives in YC Managed PostgreSQL, reachable from the Serverless Container over
the VPC (private host). Connection string comes from ``DATABASE_URL`` (injected
from Lockbox in prod).

If ``DATABASE_URL`` is empty the pool stays ``None`` and auth endpoints return
503 — the rest of the app (exams/theory/explain) keeps working without a DB,
so a missing DB never takes the whole service down.
"""

from __future__ import annotations

import ssl

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool = None  # asyncpg.Pool | None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    is_admin      BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_mastery (
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_slug  TEXT NOT NULL,
    theme_code TEXT NOT NULL,
    asked      INT NOT NULL DEFAULT 0,
    correct    INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, exam_slug, theme_code)
);
"""


def _ssl_context() -> ssl.SSLContext:
    # Managed PostgreSQL requires TLS. On the private VPC host we encrypt but
    # don't pin the YC CA (avoids baking the cert into the image). Set
    # DB_SSL_VERIFY=true + bake the CA if you want full verification.
    ctx = ssl.create_default_context()
    if not get_settings().db_ssl_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def init_pool() -> None:
    """Create the asyncpg pool and ensure the schema exists. No-op without URL."""
    global _pool
    settings = get_settings()
    if not settings.database_url:
        logger.warning("DATABASE_URL not set — auth/progress DB disabled.")
        return
    import asyncpg

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        ssl=_ssl_context(),
        min_size=1,
        max_size=5,
        command_timeout=10,
    )
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("PostgreSQL pool ready; schema ensured.")


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool():
    """Return the pool or raise 503 if the DB isn't configured."""
    if _pool is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Auth/progress database is not configured (DATABASE_URL).",
        )
    return _pool
