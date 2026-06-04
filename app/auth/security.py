"""Password hashing (bcrypt) + JWT issue/verify."""

from __future__ import annotations

import time

import bcrypt
import jwt

from app.core.config import get_settings

_ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return False


def create_token(user_id: int, email: str, is_admin: bool) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": bool(is_admin),
        "iat": now,
        "exp": now + settings.jwt_expires_h * 3600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, get_settings().jwt_secret, algorithms=[_ALGO]
        )
    except Exception:  # noqa: BLE001 — any decode/expiry error → unauthenticated
        return None
