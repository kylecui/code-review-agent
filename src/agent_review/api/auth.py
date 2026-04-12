from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from agent_review.auth.dependencies import get_current_user
from agent_review.auth.oauth import (
    build_github_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
)
from agent_review.auth.password import hash_password, verify_password
from agent_review.auth.token import create_access_token_with_secret
from agent_review.models import User
from agent_review.schemas.auth import LoginRequest, RegisterRequest, UserRead

router = APIRouter(tags=["auth"])
CurrentUser = Annotated[User, Depends(get_current_user)]


def _set_access_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _token_ttl(request: Request) -> timedelta:
    minutes = request.app.state.settings.access_token_expire_minutes
    return timedelta(minutes=minutes)


def _build_access_token(request: Request, user: User) -> str:
    secret_key = request.app.state.settings.secret_key.get_secret_value()
    return create_access_token_with_secret(
        user_id=user.id,
        is_superuser=user.is_superuser,
        secret_key=secret_key,
        expires_delta=_token_ttl(request),
    )


@router.post("/register", response_model=UserRead)
async def register(body: RegisterRequest, request: Request, response: Response) -> UserRead:
    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        count_result = await db.execute(select(func.count()).select_from(User))
        user_count = count_result.scalar_one()

        user = User(
            id=uuid.uuid4(),
            email=body.email,
            hashed_password=hash_password(body.password),
            full_name=body.full_name,
            is_superuser=(user_count == 0),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = _build_access_token(request, user)
    _set_access_token_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/login", response_model=UserRead)
async def login(body: LoginRequest, request: Request, response: Response) -> UserRead:
    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")

    token = _build_access_token(request, user)
    _set_access_token_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key="access_token", path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/github/login")
async def github_login(request: Request) -> RedirectResponse:
    settings = request.app.state.settings
    if not settings.github_oauth_client_id or not settings.oauth_redirect_uri:
        raise HTTPException(status_code=400, detail="GitHub OAuth is not configured")

    state = uuid.uuid4().hex
    request.session["github_oauth_state"] = state
    authorize_url = build_github_authorize_url(
        client_id=settings.github_oauth_client_id,
        redirect_uri=settings.oauth_redirect_uri,
        state=state,
    )
    return RedirectResponse(url=authorize_url)


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    settings = request.app.state.settings
    expected_state = request.session.get("github_oauth_state")
    if expected_state is None or expected_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token = await exchange_code_for_token(
        client_id=settings.github_oauth_client_id,
        client_secret=settings.github_oauth_client_secret.get_secret_value(),
        code=code,
    )
    github_user = await fetch_github_user(token)

    github_id_value = github_user.get("id")
    github_login = github_user.get("login")
    if not isinstance(github_id_value, int):
        raise HTTPException(status_code=400, detail="Invalid GitHub user payload")

    email = github_user.get("email")
    if not isinstance(email, str) or not email:
        email = f"github_{github_id_value}@users.noreply.github.com"
    full_name = github_user.get("name")
    if not isinstance(full_name, str):
        full_name = None

    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        existing = await db.execute(select(User).where(User.github_id == github_id_value))
        user = existing.scalar_one_or_none()

        if user is None:
            count_result = await db.execute(select(func.count()).select_from(User))
            user_count = count_result.scalar_one()
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password=hash_password(uuid.uuid4().hex),
                full_name=full_name,
                is_superuser=(user_count == 0),
                github_id=github_id_value,
                github_login=github_login if isinstance(github_login, str) else None,
            )
            db.add(user)
        else:
            user.github_login = github_login if isinstance(github_login, str) else user.github_login
            if full_name is not None:
                user.full_name = full_name

        await db.commit()
        await db.refresh(user)

    response = RedirectResponse(url="/")
    access_token = _build_access_token(request, user)
    _set_access_token_cookie(response, access_token)
    request.session.pop("github_oauth_state", None)
    return response
