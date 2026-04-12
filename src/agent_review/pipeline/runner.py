from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from agent_review.classifier.classifier import Classifier
from agent_review.collectors.base import AbstractCollector, CollectorContext
from agent_review.collectors.github_ci import GitHubCICollector
from agent_review.collectors.registry import CollectorRegistry
from agent_review.collectors.secrets import SecretsCollector
from agent_review.collectors.semgrep import SemgrepCollector
from agent_review.collectors.sonar import SonarCollector
from agent_review.gate import GateController, PolicyLoader
from agent_review.models import ReviewRun, ReviewState
from agent_review.normalize import FindingsDeduplicator, FindingsNormalizer
from agent_review.observability import RunMetrics, get_logger
from agent_review.reasoning import LLMClient, PromptManager, Synthesizer
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
                github = GitHubClient(self._http_client, auth, run.installation_id)

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.CLASSIFYING)
                await db.commit()

                pr_files = await github.get_pr_files(run.repo, run.pr_number)
                changed_files = [f["filename"] for f in pr_files if isinstance(f, dict)]

                pr_data = await github.get_pr(run.repo, run.pr_number)
                labels_obj = pr_data.get("labels", [])
                pr_labels = [
                    label["name"]
                    for label in labels_obj
                    if isinstance(label, dict) and "name" in label
                ]

                classifier = Classifier()
                classification = classifier.classify(changed_files, {})
                run.classification = classification.model_dump(mode="json")
                await db.commit()
                metrics.classification_ms = int((time.perf_counter() - stage_started) * 1000)

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.COLLECTING)
                await db.commit()

                policy_loader = PolicyLoader(self._settings.policy_dir)
                policy = policy_loader.load(run.repo)

                collectors: dict[str, AbstractCollector] = {
                    "semgrep": SemgrepCollector(self._settings, self._http_client),
                    "sonar": SonarCollector(self._settings, self._http_client),
                    "github_ci": GitHubCICollector(),
                    "secrets": SecretsCollector(),
                }
                ctx = CollectorContext(
                    repo=run.repo,
                    pr_number=run.pr_number,
                    head_sha=run.head_sha,
                    base_sha=run.base_sha,
                    changed_files=changed_files,
                    github_client=github,
                )

                registry = CollectorRegistry(collectors)
                collector_results = await registry.run_collectors(classification, ctx, policy)
                metrics.collection_ms = int((time.perf_counter() - stage_started) * 1000)
                metrics.collector_metrics = {
                    result.collector_name: {
                        "status": result.status,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                        "metadata": result.metadata,
                        "finding_count": len(result.raw_findings),
                    }
                    for result in collector_results
                }

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.NORMALIZING)
                await db.commit()

                normalizer = FindingsNormalizer()
                raw_findings = normalizer.normalize(collector_results)

                deduplicator = FindingsDeduplicator()
                findings = deduplicator.deduplicate(raw_findings)
                metrics.normalization_ms = int((time.perf_counter() - stage_started) * 1000)
                metrics.finding_count = len(findings)

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.REASONING)
                await db.commit()

                llm_client = LLMClient(self._settings)
                prompt_manager = PromptManager(self._settings.prompts_dir)
                synthesizer = Synthesizer(llm_client, prompt_manager, self._settings)
                synthesis = await synthesizer.synthesize(findings, ctx)
                metrics.reasoning_ms = int((time.perf_counter() - stage_started) * 1000)
                metrics.llm_cost_cents = synthesis.cost_cents
                metrics.is_degraded = synthesis.is_degraded

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.DECIDING)
                await db.commit()

                gate = GateController()
                decision = gate.evaluate(
                    findings=findings,
                    synthesis=synthesis,
                    classification=classification,
                    policy=policy,
                    collector_results=collector_results,
                    pr_labels=pr_labels,
                )
                run.decision = decision.model_dump(mode="json")
                await db.commit()
                metrics.gate_ms = int((time.perf_counter() - stage_started) * 1000)
                metrics.verdict = decision.verdict.value

                if await self._check_superseded(db, run):
                    return

                stage_started = time.perf_counter()
                run.transition(ReviewState.PUBLISHING)
                await db.commit()

                projection = project_decision(decision)

                await github.create_check_run(
                    repo=run.repo,
                    head_sha=run.head_sha,
                    name="Agent Review",
                    external_id=str(run.id),
                    status="completed",
                )

                summary_prompt = prompt_manager.render(
                    "summarize.j2",
                    verdict=decision.verdict.value,
                    total_findings=len(findings),
                    blocking_findings=len(decision.blocking_findings),
                    advisory_findings=len(decision.advisory_findings),
                    top_findings=[
                        finding.model_dump(mode="json")
                        for finding in findings[: policy.limits.max_summary_findings]
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
