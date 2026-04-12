from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from agent_review.models import ReviewRun, ReviewState
from agent_review.observability import RunMetrics, get_logger
from agent_review.pipeline.analysis import run_analysis
from agent_review.reasoning import PromptManager
from agent_review.scm.github_auth import GitHubAppAuth
from agent_review.scm.github_client import GitHubClient
from agent_review.scm.github_projection import project_decision

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from agent_review.config import Settings

logger = get_logger(__name__)


class PipelineRunner:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
    ):
        self._settings = settings
        self._session_factory = session_factory
        self._http_client = http_client

    async def run(self, run_id: str) -> None:
        metrics = RunMetrics(run_id=run_id)
        started_total = time.perf_counter()
        run: ReviewRun | None = None
        try:
            async with self._session_factory() as db:
                run_uuid = uuid.UUID(run_id)
                run = await db.get(ReviewRun, run_uuid)
                if run is None or run.is_terminal:
                    return

                auth = GitHubAppAuth(
                    self._settings.github_app_id,
                    self._settings.github_private_key.get_secret_value(),
                )
                if run.installation_id is None:
                    raise RuntimeError("PR pipeline requires installation_id")
                github = GitHubClient(self._http_client, auth, run.installation_id)

                if await self._check_superseded(db, run):
                    return

                pr_files = await github.get_pr_files(run.repo, run.pr_number)
                changed_files = [f["filename"] for f in pr_files if isinstance(f, dict)]

                pr_data = await github.get_pr(run.repo, run.pr_number)
                labels_obj = pr_data.get("labels", [])
                pr_labels = [
                    label["name"]
                    for label in labels_obj
                    if isinstance(label, dict) and "name" in label
                ]

                if await self._check_superseded(db, run):
                    return

                result = await run_analysis(
                    run=run,
                    db=db,
                    settings=self._settings,
                    http_client=self._http_client,
                    github=github,
                    changed_files=changed_files,
                    pr_labels=pr_labels,
                    metrics=metrics,
                )

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.PUBLISHING)
                await db.commit()

                projection = project_decision(result.decision)

                await github.create_check_run(
                    repo=run.repo,
                    head_sha=run.head_sha,
                    name="Agent Review",
                    external_id=str(run.id),
                    status="completed",
                    conclusion=projection.check_run_conclusion,
                )

                prompt_manager = PromptManager(self._settings.prompts_dir)
                summary_prompt = prompt_manager.render(
                    "summarize.j2",
                    verdict=result.decision.verdict.value,
                    total_findings=len(result.findings),
                    blocking_findings=len(result.decision.blocking_findings),
                    advisory_findings=len(result.decision.advisory_findings),
                    top_findings=[
                        finding.model_dump(mode="json")
                        for finding in result.findings[: result.policy.limits.max_summary_findings]
                    ],
                )
                await github.create_review(
                    repo=run.repo,
                    pr_number=run.pr_number,
                    commit_id=run.head_sha,
                    event=projection.review_event,
                    body=summary_prompt,
                )
                metrics.publishing_ms = int((time.perf_counter() - stage_started) * 1000)

                if await self._check_superseded(db, run):
                    return

                metrics.total_ms = int((time.perf_counter() - started_total) * 1000)
                run.transition(ReviewState.COMPLETED)
                run.metrics = metrics.to_dict()
                await db.commit()
        except Exception as exc:
            logger.error("pipeline_failed", run_id=run_id, error=str(exc))
            if run is None:
                return
            try:
                async with self._session_factory() as db:
                    run_in_db = await db.get(ReviewRun, run.id)
                    if run_in_db is None or run_in_db.is_terminal:
                        return
                    metrics.total_ms = int((time.perf_counter() - started_total) * 1000)
                    run_in_db.transition(ReviewState.FAILED)
                    run_in_db.error = str(exc)[:1000]
                    run_in_db.metrics = metrics.to_dict()
                    await db.commit()
            except Exception:
                pass

    async def _check_superseded(self, db: AsyncSession, run: ReviewRun) -> bool:
        await db.refresh(run)
        return run.state == ReviewState.SUPERSEDED
