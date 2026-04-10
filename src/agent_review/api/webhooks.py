import hashlib
import hmac
import json
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select

from agent_review.models import ReviewRun, ReviewState
from agent_review.models.enums import TriggerEvent
from agent_review.pipeline import PipelineRunner
from agent_review.pipeline.supersession import supersede_active_runs

router = APIRouter(tags=["webhooks"])


def verify_signature(payload: bytes, signature: str | None, secret: str) -> None:
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature format")

    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


TRIGGER_ACTIONS: dict[str, TriggerEvent] = {
    "opened": TriggerEvent.OPENED,
    "synchronize": TriggerEvent.SYNCHRONIZE,
    "ready_for_review": TriggerEvent.READY_FOR_REVIEW,
}


async def _run_pipeline(request: Request, run_id: str) -> None:
    settings = request.app.state.settings
    if settings.github_app_id <= 0 or not settings.github_private_key.get_secret_value().strip():
        return

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(
            settings=settings,
            session_factory=request.app.state.session_factory,
            http_client=http_client,
        )
        await runner.run(run_id)


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    raw_body = await request.body()

    settings = request.app.state.settings
    signature = request.headers.get("X-Hub-Signature-256")
    verify_signature(raw_body, signature, settings.github_webhook_secret.get_secret_value())

    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    if event_type != "pull_request":
        return {"status": "ignored", "reason": "not_pull_request"}

    payload = json.loads(raw_body)
    action = payload.get("action", "")

    trigger = TRIGGER_ACTIONS.get(action)
    if trigger is None:
        return {"status": "ignored", "reason": f"action_{action}_not_handled"}

    if payload.get("sender", {}).get("type") == "Bot":
        return {"status": "ignored", "reason": "bot_sender"}

    pr = payload.get("pull_request", {})
    if pr.get("draft", False) and action != "ready_for_review":
        return {"status": "ignored", "reason": "draft_pr"}

    repo = payload.get("repository", {}).get("full_name", "")
    pr_number = pr.get("number", 0)
    head_sha = pr.get("head", {}).get("sha", "")
    base_sha = pr.get("base", {}).get("sha", "")
    installation_id = payload.get("installation", {}).get("id", 0)

    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        existing = await db.execute(select(ReviewRun).where(ReviewRun.delivery_id == delivery_id))
        if existing.scalar_one_or_none():
            return {"status": "ignored", "reason": "duplicate_delivery"}

        existing_run = await db.execute(
            select(ReviewRun).where(
                ReviewRun.repo == repo,
                ReviewRun.pr_number == pr_number,
                ReviewRun.head_sha == head_sha,
                ReviewRun.state != ReviewState.SUPERSEDED,
            )
        )
        if existing_run.scalar_one_or_none():
            return {"status": "ignored", "reason": "duplicate_run"}

        await supersede_active_runs(db, repo, pr_number, head_sha)

        run = ReviewRun(
            id=uuid.uuid4(),
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            base_sha=base_sha,
            installation_id=installation_id,
            trigger_event=trigger,
            delivery_id=delivery_id,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)
        background_tasks.add_task(_run_pipeline, request, run_id)

    return {"status": "queued", "run_id": run_id}
