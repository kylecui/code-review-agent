import uuid

import jwt
from fastapi import HTTPException, Request

from agent_review.auth.token import decode_access_token
from agent_review.models import User


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    secret_key = request.app.state.settings.secret_key.get_secret_value()
    try:
        payload = decode_access_token(token, secret_key)
        user_id = uuid.UUID(payload.sub)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        row = await db.get(User, user_id)

    if not isinstance(row, User) or not row.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return row


async def get_current_superuser(request: Request) -> User:
    user = await get_current_user(request)
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user
