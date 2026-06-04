"""FastAPI auth dependencies: current user + admin gate."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.auth.security import decode_token


@dataclass
class CurrentUser:
    id: int
    email: str
    is_admin: bool


def _from_header(authorization: str | None) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Требуется вход (нет токена).")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново.")
    return CurrentUser(
        id=int(payload["sub"]),
        email=str(payload.get("email", "")),
        is_admin=bool(payload.get("is_admin", False)),
    )


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    return _from_header(authorization)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Доступ только для администратора.")
    return user
