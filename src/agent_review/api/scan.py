from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from agent_review.models import ReviewRun, RunKind
from agent_review.pipeline.baseline_runner import BaselineRunner
from agent_review.pipeline.local_runner import LocalBaselineRunner
from agent_review.schemas.review_run import ReviewRunRead, ScanRequest
from agent_review.scm.github_auth import GitHubAppAuth
from agent_review.scm.github_client import GitHubClient

if TYPE_CHECKING:
    from agent_review.config import Settings

router = APIRouter(tags=["scan"])


async def _resolve_head_sha(
    github: GitHubClient, repo: str, ref: str | None, branch: str | None
) -> str:
    if ref:
        return ref
    if branch:
        return await github.get_branch_sha(repo, branch)
    default_branch = await github.get_default_branch(repo)
    return await github.get_branch_sha(repo, default_branch)


def _path_hash(path: str) -> str:
    return hashlib.sha1(path.encode()).hexdigest()


async def _run_baseline(request: Request, run_id: str) -> None:
    settings: Settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=120.0) as http_client:
        runner = BaselineRunner(
            settings=settings,
            session_factory=request.app.state.session_factory,
            http_client=http_client,
        )
        await runner.run(run_id)


async def _run_local_baseline(request: Request, run_id: str, local_path: str) -> None:
    settings: Settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=120.0) as http_client:
        runner = LocalBaselineRunner(
            settings=settings,
            session_factory=request.app.state.session_factory,
            http_client=http_client,
        )
        await runner.run(run_id, local_path)


@router.post("/scan", status_code=202)
async def create_scan(
    body: ScanRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    is_local = body.path is not None

    if is_local:
        local_path = body.path
        assert local_path is not None
        if not Path(local_path).is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Local path does not exist or is not a directory: {local_path}",
            )
        head_sha = _path_hash(local_path)
        run = ReviewRun(
            id=uuid.uuid4(),
            repo=body.repo,
            run_kind=RunKind.BASELINE,
            pr_number=None,
            head_sha=head_sha,
            base_sha=None,
            installation_id=None,
            trigger_event=None,
            delivery_id=None,
        )
        async with session_factory() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = str(run.id)

        background_tasks.add_task(_run_local_baseline, request, run_id, local_path)
        return {"status": "queued", "run_id": run_id}

    auth = GitHubAppAuth(
        settings.github_app_id,
        settings.github_private_key.get_secret_value(),
    )

    installation_id = body.installation_id
    if installation_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "installation_id is required for GitHub scans (or provide 'path' for local scan)"
            ),
        )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        github = GitHubClient(http_client, auth, installation_id)
        head_sha = await _resolve_head_sha(github, body.repo, body.ref, body.branch)

    run = ReviewRun(
        id=uuid.uuid4(),
        repo=body.repo,
        run_kind=RunKind.BASELINE,
        pr_number=None,
        head_sha=head_sha,
        base_sha=None,
        installation_id=installation_id,
        trigger_event=None,
        delivery_id=None,
    )

    async with session_factory() as db:
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)

    background_tasks.add_task(_run_baseline, request, run_id)
    return {"status": "queued", "run_id": run_id}


@router.get("/scan/{run_id}")
async def get_scan_status(run_id: str, request: Request) -> ReviewRunRead:
    session_factory = request.app.state.session_factory
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run_id format") from exc

    async with session_factory() as db:
        run = await db.get(ReviewRun, run_uuid)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return ReviewRunRead.model_validate(run)
