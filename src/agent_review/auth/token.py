from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt

from agent_review.schemas.auth import TokenPayload

_DEFAULT_SECRET_KEY = "change-me-in-production"

if TYPE_CHECKING:
    import uuid


def create_access_token(
    user_id: uuid.UUID,
    is_superuser: bool,
    expires_delta: timedelta | None = None,
) -> str:
    secret_key = os.getenv("AGENT_REVIEW_SECRET_KEY", _DEFAULT_SECRET_KEY)
    return create_access_token_with_secret(user_id, is_superuser, secret_key, expires_delta)


def create_access_token_with_secret(
    user_id: uuid.UUID,
    is_superuser: bool,
    secret_key: str,
    expires_delta: timedelta | None = None,
) -> str:
    expires_in = expires_delta if expires_delta is not None else timedelta(minutes=60)
    expire = datetime.now(UTC) + expires_in
    payload = {
        "sub": str(user_id),
        "is_superuser": is_superuser,
        "exp": expire,
    }
    return jwt.encode(payload, key=secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> TokenPayload:
    payload = jwt.decode(token, key=secret_key, algorithms=["HS256"])
    return TokenPayload.model_validate(payload)
