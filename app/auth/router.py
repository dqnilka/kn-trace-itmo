"""Auth + server-side progress endpoints.

  POST /api/v1/auth/register   {email, password, display_name?}
  POST /api/v1/auth/login      {email, password}
  GET  /api/v1/auth/me
  GET  /api/v1/me/mastery?exam_slug=fsfr-basic
  POST /api/v1/me/event        {exam_slug, theme_code, is_correct}

Progress (user_mastery) is the server source of truth; the frontend keeps a
localStorage cache and syncs through these endpoints.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import CurrentUser, get_current_user
from app.auth.security import create_token, hash_password, verify_password
from app.core.config import get_settings
from app.core.db import get_pool
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    is_admin: bool


class AuthResponse(BaseModel):
    token: str
    user: UserOut


def _norm_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Некорректный email.")
    return email


@router.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    email = _norm_email(req.email)
    is_admin = email in get_settings().admin_email_set
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT 1 FROM users WHERE email=$1", email)
        if existing:
            raise HTTPException(status_code=409, detail="Пользователь с таким email уже есть.")
        row = await conn.fetchrow(
            """INSERT INTO users (email, password_hash, display_name, is_admin)
               VALUES ($1,$2,$3,$4) RETURNING id, email, display_name, is_admin""",
            email, hash_password(req.password), req.display_name, is_admin,
        )
    user = UserOut(**dict(row))
    return AuthResponse(token=create_token(user.id, user.email, user.is_admin), user=user)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    email = _norm_email(req.email)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, is_admin, password_hash FROM users WHERE email=$1",
            email,
        )
        if not row or not verify_password(req.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный email или пароль.")
        # Bootstrap promotion: keep is_admin in sync with ADMIN_EMAILS.
        is_admin = bool(row["is_admin"]) or email in get_settings().admin_email_set
        if is_admin and not row["is_admin"]:
            await conn.execute("UPDATE users SET is_admin=true WHERE id=$1", row["id"])
    user = UserOut(id=row["id"], email=row["email"], display_name=row["display_name"], is_admin=is_admin)
    return AuthResponse(token=create_token(user.id, user.email, user.is_admin), user=user)


@router.get("/auth/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, is_admin FROM users WHERE id=$1", user.id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    return UserOut(**dict(row))


class MasteryEvent(BaseModel):
    exam_slug: str
    theme_code: str
    is_correct: bool


@router.get("/me/mastery")
async def get_my_mastery(
    exam_slug: str = "fsfr-basic", user: CurrentUser = Depends(get_current_user)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT theme_code, asked, correct FROM user_mastery WHERE user_id=$1 AND exam_slug=$2",
            user.id, exam_slug,
        )
    return {
        "exam_slug": exam_slug,
        "themes": {
            r["theme_code"]: {"asked": r["asked"], "correct": r["correct"]} for r in rows
        },
    }


class MasteryThemeState(BaseModel):
    asked: int = 0
    correct: int = 0


class MasterySync(BaseModel):
    exam_slug: str = "fsfr-basic"
    themes: dict[str, MasteryThemeState]


@router.put("/me/mastery")
async def put_my_mastery(body: MasterySync, user: CurrentUser = Depends(get_current_user)):
    """Idempotent absolute upsert of the user's per-theme progress. The client
    pushes its full local store at lesson/entrance boundaries — no double count."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for code, st in body.themes.items():
                await conn.execute(
                    """INSERT INTO user_mastery (user_id, exam_slug, theme_code, asked, correct, updated_at)
                       VALUES ($1,$2,$3,$4,$5, now())
                       ON CONFLICT (user_id, exam_slug, theme_code) DO UPDATE
                       SET asked = EXCLUDED.asked, correct = EXCLUDED.correct, updated_at = now()""",
                    user.id, body.exam_slug, code, max(0, st.asked), max(0, st.correct),
                )
    return {"ok": True, "themes": len(body.themes)}


class FeedbackIn(BaseModel):
    kind: str  # 'theory' | 'lesson'
    ref: str = ''  # theme_code / lesson id
    rating: str  # 'like' | 'dislike'
    comment: str | None = None


@router.post("/me/feedback")
async def submit_feedback(fb: FeedbackIn, user: CurrentUser = Depends(get_current_user)):
    if fb.kind not in ('theory', 'lesson') or fb.rating not in ('like', 'dislike'):
        raise HTTPException(status_code=422, detail="Некорректный kind/rating.")
    comment = (fb.comment or '').strip()[:2000] or None
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO feedback (user_id, kind, ref, rating, comment)
               VALUES ($1,$2,$3,$4,$5)""",
            user.id, fb.kind, fb.ref[:128], fb.rating, comment,
        )
    return {"ok": True}


@router.post("/me/event")
async def record_my_event(ev: MasteryEvent, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO user_mastery (user_id, exam_slug, theme_code, asked, correct, updated_at)
               VALUES ($1,$2,$3,1,$4, now())
               ON CONFLICT (user_id, exam_slug, theme_code) DO UPDATE
               SET asked = user_mastery.asked + 1,
                   correct = user_mastery.correct + $4,
                   updated_at = now()""",
            user.id, ev.exam_slug, ev.theme_code, 1 if ev.is_correct else 0,
        )
    return {"ok": True}
