from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy import select

from agent_review.classifier.classifier import Classifier
from agent_review.collectors.base import AbstractCollector, CollectorContext
from agent_review.collectors.github_ci import GitHubCICollector
from agent_review.collectors.registry import CollectorRegistry
from agent_review.collectors.secrets import SecretsCollector
from agent_review.collectors.semgrep import SemgrepCollector
from agent_review.collectors.sonar import SonarCollector
from agent_review.crypto import decrypt_value
from agent_review.gate import GateController, PolicyLoader
from agent_review.models import Finding
from agent_review.models.app_config import AppConfig
from agent_review.normalize import FindingsDeduplicator, FindingsNormalizer
from agent_review.reasoning import LLMClient, PromptManager, Synthesizer

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from agent_review.collectors.base import CollectorResult
    from agent_review.config import Settings
    from agent_review.models import ReviewRun
    from agent_review.observability import RunMetrics
    from agent_review.reasoning.synthesizer import SynthesisResult
    from agent_review.schemas.classification import Classification
    from agent_review.schemas.decision import ReviewDecision
    from agent_review.schemas.finding import FindingCreate
    from agent_review.schemas.policy import PolicyConfig
    from agent_review.scm.github_client import GitHubClient


@dataclass
class AnalysisResult:
    classification: Classification
    findings: list[FindingCreate]
    synthesis: SynthesisResult
    decision: ReviewDecision
    collector_results: list[CollectorResult]
    policy: PolicyConfig
    metrics: RunMetrics


async def run_analysis(
    *,
    run: ReviewRun,
    db: AsyncSession,
    settings: Settings,
    http_client: httpx.AsyncClient,
    github: GitHubClient | None,
    changed_files: list[str],
    pr_labels: list[str],
    metrics: RunMetrics,
    local_path: str | None = None,
) -> AnalysisResult:
    stage_started = time.perf_counter()
    await _do_transition(db, run, "CLASSIFYING")

    classifier = Classifier()
    classification = classifier.classify(changed_files, {})
    run.classification = classification.model_dump(mode="json")
    await db.commit()
    metrics.classification_ms = int((time.perf_counter() - stage_started) * 1000)

    stage_started = time.perf_counter()
    await _do_transition(db, run, "COLLECTING")

    policy_loader = PolicyLoader(settings.policy_dir)
    policy = policy_loader.load(run.repo)

    collectors: dict[str, AbstractCollector] = {
        "semgrep": SemgrepCollector(settings, http_client),
        "sonar": SonarCollector(settings, http_client),
        "github_ci": GitHubCICollector(),
        "secrets": SecretsCollector(),
    }
    ctx = CollectorContext(
        repo=run.repo,
        head_sha=run.head_sha,
        changed_files=changed_files,
        github_client=github,
        run_kind=run.run_kind.value if hasattr(run.run_kind, "value") else "pr",
        pr_number=run.pr_number,
        base_sha=run.base_sha,
        local_path=local_path,
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

    stage_started = time.perf_counter()
    await _do_transition(db, run, "NORMALIZING")

    normalizer = FindingsNormalizer()
    raw_findings = normalizer.normalize(collector_results)
    deduplicator = FindingsDeduplicator()
    findings = deduplicator.deduplicate(raw_findings)
    for f in findings:
        db.add(
            Finding(
                id=uuid.uuid4(),
                review_run_id=run.id,
                finding_id=f.finding_id,
                category=f.category,
                severity=f.severity,
                confidence=f.confidence,
                blocking=f.blocking,
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                source_tools=f.source_tools,
                rule_id=f.rule_id,
                title=f.title,
                evidence=f.evidence,
                impact=f.impact,
                fix_recommendation=f.fix_recommendation,
                test_recommendation=f.test_recommendation,
                fingerprint=f.fingerprint,
                disposition=f.disposition,
            )
        )
    await db.commit()
    metrics.normalization_ms = int((time.perf_counter() - stage_started) * 1000)
    metrics.finding_count = len(findings)

    stage_started = time.perf_counter()
    await _do_transition(db, run, "REASONING")

    api_keys: dict[str, str] = {}
    secret = settings.secret_key.get_secret_value()
    key_names = [
        "llm_openai_api_key",
        "llm_gemini_api_key",
        "llm_github_api_key",
        "llm_anthropic_api_key",
    ]
    result = await db.execute(select(AppConfig).where(AppConfig.key.in_(key_names)))
    overrides = {r.key: r for r in result.scalars().all()}
    for k in key_names:
        override = overrides.get(k)
        if override is not None:
            import json

            decrypted = decrypt_value(json.loads(override.value), secret)
            if decrypted:
                api_keys[k] = decrypted
                continue
        env_val = getattr(settings, k, None)
        if isinstance(env_val, SecretStr) and env_val.get_secret_value():
            api_keys[k] = env_val.get_secret_value()

    llm_client = LLMClient(settings, api_keys=api_keys)
    prompt_manager = PromptManager(settings.prompts_dir)
    synthesizer = Synthesizer(llm_client, prompt_manager, settings)
    synthesis = await synthesizer.synthesize(findings, ctx)
    metrics.reasoning_ms = int((time.perf_counter() - stage_started) * 1000)
    metrics.llm_cost_cents = synthesis.cost_cents
    metrics.is_degraded = synthesis.is_degraded

    stage_started = time.perf_counter()
    await _do_transition(db, run, "DECIDING")

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

    return AnalysisResult(
        classification=classification,
        findings=findings,
        synthesis=synthesis,
        decision=decision,
        collector_results=collector_results,
        policy=policy,
        metrics=metrics,
    )


async def _do_transition(
    db: AsyncSession,
    run: ReviewRun,
    state_name: str,
) -> None:
    from agent_review.models import ReviewState

    run.transition(ReviewState[state_name])
    await db.commit()
