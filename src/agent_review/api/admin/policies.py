from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Annotated, Any

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from agent_review.auth.dependencies import get_current_superuser
from agent_review.models import User
from agent_review.models.policy_store import PolicyStore
from agent_review.schemas.policy import PolicyConfig

router = APIRouter(tags=["admin-policies"])
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]


class PolicyPutBody(BaseModel):
    content: str


def _compute_etag(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _validate_policy_yaml(content: str) -> None:
    try:
        raw_data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc

    if raw_data is None:
        normalized_data: dict[str, Any] = {}
    elif isinstance(raw_data, dict):
        normalized_data = {str(key): value for key, value in raw_data.items()}
    else:
        raise HTTPException(status_code=422, detail="Policy YAML must be a mapping")

    try:
        PolicyConfig.model_validate(normalized_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid policy schema: {exc}") from exc


def _set_etag_header(response: Response, etag: str) -> None:
    response.headers["ETag"] = f'"{etag}"'


@router.get("/")
async def list_policies(request: Request, current_user: CurrentSuperuser) -> list[dict[str, Any]]:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(select(PolicyStore).order_by(PolicyStore.name.asc()))
        policies = result.scalars().all()

    return [{"name": p.name, "etag": p.etag, "updated_at": p.updated_at} for p in policies]


@router.post("/seed")
async def seed_policies(request: Request, current_user: CurrentSuperuser) -> dict[str, list[str]]:
    session_factory = request.app.state.session_factory
    policy_dir = Path(request.app.state.settings.policy_dir)

    imported: list[str] = []
    skipped: list[str] = []

    async with session_factory() as db:
        for policy_file in sorted(policy_dir.rglob("*.yaml")):
            name = policy_file.stem
            result = await db.execute(select(PolicyStore).where(PolicyStore.name == name))
            existing = result.scalar_one_or_none()
            if existing is not None:
                skipped.append(name)
                continue

            content = policy_file.read_text(encoding="utf-8")
            _validate_policy_yaml(content)
            db.add(
                PolicyStore(
                    id=uuid.uuid4(),
                    name=name,
                    content=content,
                    etag=_compute_etag(content),
                    updated_by=current_user.id,
                )
            )
            imported.append(name)

        await db.commit()

    return {"imported": imported, "skipped": skipped}


@router.get("/{name:path}")
async def get_policy(
    name: str,
    request: Request,
    response: Response,
    current_user: CurrentSuperuser,
) -> dict[str, str]:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(select(PolicyStore).where(PolicyStore.name == name))
        policy = result.scalar_one_or_none()

    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    _set_etag_header(response, policy.etag)
    return {"name": policy.name, "content": policy.content, "etag": policy.etag}


@router.put("/{name:path}")
async def put_policy(
    name: str,
    body: PolicyPutBody,
    request: Request,
    response: Response,
    current_user: CurrentSuperuser,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> dict[str, str]:
    session_factory = request.app.state.session_factory

    _validate_policy_yaml(body.content)
    new_etag = _compute_etag(body.content)

    async with session_factory() as db:
        result = await db.execute(select(PolicyStore).where(PolicyStore.name == name))
        existing = result.scalar_one_or_none()

        if existing is None:
            existing = PolicyStore(
                id=uuid.uuid4(),
                name=name,
                content=body.content,
                etag=new_etag,
                updated_by=current_user.id,
            )
            db.add(existing)
        else:
            if if_match is None:
                raise HTTPException(status_code=428, detail="Missing If-Match header")

            normalized_if_match = if_match.strip().strip('"')
            if normalized_if_match != existing.etag:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "ETag mismatch",
                        "current": {
                            "name": existing.name,
                            "content": existing.content,
                            "etag": existing.etag,
                        },
                    },
                )

            existing.content = body.content
            existing.etag = new_etag
            existing.updated_by = current_user.id

        await db.commit()
        await db.refresh(existing)

    _set_etag_header(response, existing.etag)
    return {"name": existing.name, "content": existing.content, "etag": existing.etag}


@router.delete("/{name:path}")
async def delete_policy(
    name: str,
    request: Request,
    current_user: CurrentSuperuser,
) -> dict[str, str]:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(select(PolicyStore).where(PolicyStore.name == name))
        policy = result.scalar_one_or_none()
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy not found")

        await db.delete(policy)
        await db.commit()

    return {"status": "ok"}
