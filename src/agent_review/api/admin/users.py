from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from agent_review.auth.dependencies import get_current_superuser
from agent_review.auth.password import hash_password
from agent_review.models import User
from agent_review.schemas.auth import UserCreate, UserRead, UserUpdate

router = APIRouter(tags=["admin-users"])
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]


@router.get("/", response_model=list[UserRead])
async def list_users(
    request: Request,
    current_user: CurrentSuperuser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[UserRead]:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(
            select(User).order_by(User.created_at.asc()).offset(skip).limit(limit)
        )
        users = result.scalars().all()
    return [UserRead.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentSuperuser,
) -> UserRead:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    current_user: CurrentSuperuser,
) -> UserRead:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            id=uuid.uuid4(),
            email=body.email,
            hashed_password=hash_password(body.password),
            full_name=body.full_name,
            is_superuser=body.is_superuser,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    current_user: CurrentSuperuser,
) -> UserRead:
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if user.id == current_user.id:
            if body.is_superuser is False:
                raise HTTPException(status_code=400, detail="Cannot remove own superuser flag")
            if body.is_active is False:
                raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

        if body.email is not None and body.email != user.email:
            existing = await db.execute(select(User).where(User.email == body.email))
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="Email already registered")
            user.email = body.email

        if body.password is not None:
            user.hashed_password = hash_password(body.password)
        if body.full_name is not None:
            user.full_name = body.full_name
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.is_superuser is not None:
            user.is_superuser = body.is_superuser

        await db.commit()
        await db.refresh(user)

    return UserRead.model_validate(user)


@router.delete("/{user_id}", response_model=UserRead)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: CurrentSuperuser,
) -> UserRead:
    session_factory = request.app.state.session_factory

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    async with session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False
        await db.commit()
        await db.refresh(user)
    return UserRead.model_validate(user)
