from __future__ import annotations

import uuid
from typing import Annotated, Any, ClassVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent_review.auth.dependencies import get_current_superuser, get_current_user
from agent_review.models import InvalidTransition, ReviewRun, ReviewState, RunKind, User
from agent_review.schemas.finding import FindingRead
from agent_review.schemas.review_run import ReviewRunRead

router = APIRouter(tags=["admin-scans"])
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]


class PaginatedScans(BaseModel):
    items: list[ReviewRunRead]
    total: int
    page: int
    page_size: int


class ScanDetailResponse(BaseModel):
    scan: ReviewRunRead
    findings: list[FindingRead]


class TriggerScanBody(BaseModel):
    repo: str | None = None
    installation_id: int | None = None
    path: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


def _parse_state_filter(raw_state: str | None) -> ReviewState | None:
    if raw_state is None:
        return None
    try:
        return ReviewState(raw_state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid state: {raw_state}") from exc


def _parse_kind_filter(raw_kind: str | None) -> RunKind | None:
    if raw_kind is None:
        return None
    try:
        return RunKind(raw_kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid kind: {raw_kind}") from exc


@router.get("/", response_model=PaginatedScans)
async def list_scans(
    request: Request,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    repo: str | None = Query(default=None),
    state: str | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> PaginatedScans:
    _ = current_user
    session_factory = request.app.state.session_factory

    parsed_state = _parse_state_filter(state)
    parsed_kind = _parse_kind_filter(kind)

    filters: list[Any] = []
    if repo is not None:
        filters.append(ReviewRun.repo == repo)
    if parsed_state is not None:
        filters.append(ReviewRun.state == parsed_state)
    if parsed_kind is not None:
        filters.append(ReviewRun.run_kind == parsed_kind)

    offset = (page - 1) * page_size

    async with session_factory() as db:
        count_stmt = select(func.count()).select_from(ReviewRun)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = (await db.execute(count_stmt)).scalar_one()

        scans_stmt = select(ReviewRun)
        if filters:
            scans_stmt = scans_stmt.where(*filters)
        scans_stmt = (
            scans_stmt.order_by(ReviewRun.created_at.desc()).offset(offset).limit(page_size)
        )
        result = await db.execute(scans_stmt)
        scans = result.scalars().all()

    return PaginatedScans(
        items=[ReviewRunRead.model_validate(scan) for scan in scans],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan(
    scan_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
) -> ScanDetailResponse:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(
            select(ReviewRun)
            .options(selectinload(ReviewRun.findings))
            .where(ReviewRun.id == scan_id)
        )
        scan = result.scalar_one_or_none()

    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanDetailResponse(
        scan=ReviewRunRead.model_validate(scan),
        findings=[FindingRead.model_validate(finding) for finding in scan.findings],
    )


@router.post("/trigger", response_model=ReviewRunRead, status_code=status.HTTP_202_ACCEPTED)
async def trigger_scan(
    body: TriggerScanBody,
    request: Request,
    current_user: CurrentSuperuser,
) -> ReviewRunRead:
    _ = current_user
    if body.repo is None and body.path is None:
        raise HTTPException(status_code=422, detail="Either 'repo' or 'path' must be provided")

    session_factory = request.app.state.session_factory
    head_sha = f"{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
    run = ReviewRun(
        id=uuid.uuid4(),
        repo=body.repo or body.path or "local/path",
        run_kind=RunKind.BASELINE,
        head_sha=head_sha,
        state=ReviewState.PENDING,
        installation_id=body.installation_id,
    )

    async with session_factory() as db:
        db.add(run)
        await db.commit()
        await db.refresh(run)

    return ReviewRunRead.model_validate(run)


@router.post("/{scan_id}/cancel", response_model=ReviewRunRead)
async def cancel_scan(
    scan_id: uuid.UUID,
    request: Request,
    current_user: CurrentSuperuser,
) -> ReviewRunRead:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        scan = await db.get(ReviewRun, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        if scan.is_terminal:
            raise HTTPException(status_code=400, detail="Scan is already terminal")

        try:
            scan.transition(ReviewState.SUPERSEDED)
        except InvalidTransition:
            scan.transition(ReviewState.FAILED)

        await db.commit()
        await db.refresh(scan)

    return ReviewRunRead.model_validate(scan)


@router.delete("/{scan_id}", response_model=ReviewRunRead)
async def delete_scan(
    scan_id: uuid.UUID,
    request: Request,
    current_user: CurrentSuperuser,
) -> ReviewRunRead:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        result = await db.execute(
            select(ReviewRun)
            .options(selectinload(ReviewRun.findings))
            .where(ReviewRun.id == scan_id)
        )
        scan = result.scalar_one_or_none()
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")

        payload = ReviewRunRead.model_validate(scan)

        for finding in scan.findings:
            await db.delete(finding)
        await db.delete(scan)
        await db.commit()

    return payload
