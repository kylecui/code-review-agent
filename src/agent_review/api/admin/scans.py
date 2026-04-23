from __future__ import annotations

import hashlib
import json as json_mod
import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent_review.auth.dependencies import get_current_superuser, get_current_user
from agent_review.models import InvalidTransition, ReviewRun, ReviewState, RunKind, User
from agent_review.pipeline.baseline_runner import BaselineRunner
from agent_review.pipeline.local_runner import LocalBaselineRunner
from agent_review.reporting.db_report import build_json_report, build_markdown_report
from agent_review.schemas.finding import FindingRead
from agent_review.schemas.review_run import ReviewRunRead

router = APIRouter(tags=["admin-scans"])
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/gzip",
        "application/x-gzip",
        "application/x-tar",
        "application/x-compressed-tar",
        "application/octet-stream",
    }
)

ALLOWED_EXTENSIONS = frozenset({".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"})


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


def _validate_upload_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=422, detail="Uploaded file must have a filename")
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return filename


def _extract_archive(archive_path: Path, extract_dir: Path) -> Path:
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_dir)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            tf.extractall(extract_dir, filter="data")
    else:
        raise HTTPException(status_code=422, detail="File is not a valid zip or tar archive")

    children = list(extract_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extract_dir


async def _run_upload_scan(
    request: Request, run_id: str, local_path: str, cleanup_dir: str
) -> None:
    settings = request.app.state.settings
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            runner = LocalBaselineRunner(
                settings=settings,
                session_factory=request.app.state.session_factory,
                http_client=http_client,
            )
            await runner.run(run_id, local_path)
    finally:
        shutil.rmtree(cleanup_dir, ignore_errors=True)


async def _run_github_baseline(request: Request, run_id: str) -> None:
    settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=120.0) as http_client:
        runner = BaselineRunner(
            settings=settings,
            session_factory=request.app.state.session_factory,
            http_client=http_client,
        )
        await runner.run(run_id)


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


@router.get("/{scan_id}/report")
async def export_report(
    scan_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    fmt: Literal["markdown", "json"] = Query(default="markdown", alias="format"),
) -> Response:
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

    scan_dict = ReviewRunRead.model_validate(scan).model_dump(mode="json")
    findings_dicts = [FindingRead.model_validate(f).model_dump(mode="json") for f in scan.findings]

    repo_slug = scan.repo.replace("/", "_")

    if fmt == "json":
        body = json_mod.dumps(build_json_report(scan_dict, findings_dicts), indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="report_{repo_slug}_{scan_id}.json"'
            },
        )

    body = build_markdown_report(scan_dict, findings_dicts)
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report_{repo_slug}_{scan_id}.md"'},
    )


@router.get("/{scan_id}/logs")
async def get_scan_logs(
    scan_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    level: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    _ = current_user
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        scan = await db.get(ReviewRun, scan_id)

    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    logs: list[dict[str, Any]] = scan.run_logs or []

    if level:
        upper = level.upper()
        logs = [entry for entry in logs if entry.get("level") == upper]

    return logs


@router.post("/trigger", response_model=ReviewRunRead, status_code=status.HTTP_202_ACCEPTED)
async def trigger_scan(
    body: TriggerScanBody,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentSuperuser,
) -> ReviewRunRead:
    _ = current_user
    if body.repo is None:
        raise HTTPException(status_code=422, detail="'repo' is required (owner/name)")

    settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    from agent_review.scm.github_auth import GitHubAppAuth
    from agent_review.scm.github_client import GitHubClient

    auth = GitHubAppAuth(
        settings.github_app_id,
        settings.github_private_key.get_secret_value(),
    )

    installation_id = body.installation_id
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        if installation_id is None:
            try:
                installation_id = await auth.discover_installation_id(body.repo, http_client)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        github = GitHubClient(http_client, auth, installation_id)
        default_branch = await github.get_default_branch(body.repo)
        head_sha = await github.get_branch_sha(body.repo, default_branch)

    run = ReviewRun(
        id=uuid.uuid4(),
        repo=body.repo,
        run_kind=RunKind.BASELINE,
        head_sha=head_sha,
        state=ReviewState.PENDING,
        installation_id=installation_id,
    )

    async with session_factory() as db:
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)

    background_tasks.add_task(_run_github_baseline, request, run_id)
    return ReviewRunRead.model_validate(run)


@router.post("/upload", response_model=ReviewRunRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentSuperuser,
    file: UploadFile = ...,
) -> ReviewRunRead:
    _ = current_user
    settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    filename = _validate_upload_filename(file.filename)

    upload_base = Path(settings.upload_dir)
    upload_base.mkdir(parents=True, exist_ok=True)

    run_uuid = uuid.uuid4()
    job_dir = upload_base / str(run_uuid)
    job_dir.mkdir()

    archive_path = job_dir / filename
    try:
        total_bytes = 0
        with archive_path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.upload_max_bytes:
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File too large. Maximum size: "
                            f"{settings.upload_max_bytes // (1024 * 1024)} MB"
                        ),
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from None

    extract_dir = job_dir / "extracted"
    extract_dir.mkdir()
    try:
        project_root = _extract_archive(archive_path, extract_dir)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Failed to extract archive") from None

    archive_path.unlink(missing_ok=True)

    project_name = project_root.name if project_root != extract_dir else Path(filename).stem
    head_sha = hashlib.sha1(f"{run_uuid}:{filename}".encode()).hexdigest()

    run = ReviewRun(
        id=run_uuid,
        repo=f"upload/{project_name}",
        run_kind=RunKind.BASELINE,
        head_sha=head_sha,
        state=ReviewState.PENDING,
        installation_id=None,
    )

    async with session_factory() as db:
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)

    background_tasks.add_task(_run_upload_scan, request, run_id, str(project_root), str(job_dir))
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
