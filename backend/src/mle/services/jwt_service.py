from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt

from mle.core.config import get_settings


def create_access_token(*, user_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=settings.jwt_expires_hours)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    data = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    sub = data.get("sub")
    if not sub or not isinstance(sub, str):
        raise ValueError("invalid_token")
    return UUID(sub)
