from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from agent_review.auth.dependencies import get_current_user
from agent_review.crypto import decrypt_value, encrypt_value, mask_secret
from agent_review.models import User
from agent_review.models.user_repository import UserRepository

router = APIRouter(tags=["user-repositories"])
CurrentUser = Annotated[User, Depends(get_current_user)]


class RepoCreate(BaseModel):
    repo_url: str
    repo_name: str
    provider: str = "github"
    auth_token: str | None = None
    default_branch: str = "main"


class RepoUpdate(BaseModel):
    repo_name: str | None = None
    provider: str | None = None
    auth_token: str | None = None
    default_branch: str | None = None
    scan_enabled: bool | None = None


def _repo_payload(repo: UserRepository, secret_key: str) -> dict[str, Any]:
    auth_token: str | None = None
    if repo.auth_token:
        decrypted = decrypt_value(json.loads(repo.auth_token), secret_key)
        auth_token = mask_secret(decrypted)

    return {
        "id": str(repo.id),
        "user_id": str(repo.user_id),
        "repo_url": repo.repo_url,
        "repo_name": repo.repo_name,
        "provider": repo.provider,
        "auth_token": auth_token,
        "default_branch": repo.default_branch,
        "scan_enabled": repo.scan_enabled,
        "created_at": repo.created_at.isoformat(),
        "updated_at": repo.updated_at.isoformat(),
    }


@router.get("/")
async def list_repositories(
    request: Request, current_user: CurrentUser
) -> dict[str, list[dict[str, Any]]]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(
            select(UserRepository)
            .where(UserRepository.user_id == current_user.id)
            .order_by(UserRepository.created_at.asc())
        )
        repos = result.scalars().all()

    return {"repositories": [_repo_payload(repo, secret_key) for repo in repos]}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepoCreate, request: Request, current_user: CurrentUser
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    auth_token: str | None = None
    if body.auth_token:
        auth_token = json.dumps(encrypt_value(body.auth_token, secret_key))

    repo = UserRepository(
        id=uuid.uuid4(),
        user_id=current_user.id,
        repo_url=body.repo_url,
        repo_name=body.repo_name,
        provider=body.provider,
        auth_token=auth_token,
        default_branch=body.default_branch,
    )

    async with session_factory() as db:
        db.add(repo)
        await db.commit()
        await db.refresh(repo)

    return _repo_payload(repo, secret_key)


@router.get("/{repo_id}")
async def get_repository(
    repo_id: uuid.UUID, request: Request, current_user: CurrentUser
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(
            select(UserRepository).where(
                UserRepository.id == repo_id,
                UserRepository.user_id == current_user.id,
            )
        )
        repo = result.scalar_one_or_none()

    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    return _repo_payload(repo, secret_key)


@router.put("/{repo_id}")
async def update_repository(
    repo_id: uuid.UUID, body: RepoUpdate, request: Request, current_user: CurrentUser
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(
            select(UserRepository).where(
                UserRepository.id == repo_id,
                UserRepository.user_id == current_user.id,
            )
        )
        repo = result.scalar_one_or_none()
        if repo is None:
            raise HTTPException(status_code=404, detail="Repository not found")

        if body.repo_name is not None:
            repo.repo_name = body.repo_name
        if body.provider is not None:
            repo.provider = body.provider
        if body.default_branch is not None:
            repo.default_branch = body.default_branch
        if body.scan_enabled is not None:
            repo.scan_enabled = body.scan_enabled
        if body.auth_token is not None and "****" not in body.auth_token:
            if body.auth_token == "":
                repo.auth_token = None
            else:
                repo.auth_token = json.dumps(encrypt_value(body.auth_token, secret_key))

        await db.commit()
        await db.refresh(repo)

    return _repo_payload(repo, secret_key)


@router.delete("/{repo_id}")
async def delete_repository(
    repo_id: uuid.UUID, request: Request, current_user: CurrentUser
) -> dict[str, str]:
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(
            select(UserRepository).where(
                UserRepository.id == repo_id,
                UserRepository.user_id == current_user.id,
            )
        )
        repo = result.scalar_one_or_none()
        if repo is None:
            raise HTTPException(status_code=404, detail="Repository not found")

        await db.delete(repo)
        await db.commit()

    return {"status": "ok"}


@router.post("/{repo_id}/test")
async def test_repository_connection(
    repo_id: uuid.UUID, request: Request, current_user: CurrentUser
) -> dict[str, str]:
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(
            select(UserRepository).where(
                UserRepository.id == repo_id,
                UserRepository.user_id == current_user.id,
            )
        )
        repo = result.scalar_one_or_none()

    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    return {"status": "ok", "message": "Connection test not yet implemented"}
