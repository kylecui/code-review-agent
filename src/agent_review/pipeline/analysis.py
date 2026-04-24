from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import SecretStr
from sqlalchemy import select

from agent_review.classifier.classifier import Classifier
from agent_review.collectors.base import AbstractCollector, CollectorContext
from agent_review.collectors.codeql import CodeQLCollector
from agent_review.collectors.cppcheck import CppcheckCollector
from agent_review.collectors.eslint_security import EslintSecurityCollector
from agent_review.collectors.github_ci import GitHubCICollector
from agent_review.collectors.gitleaks import GitleaksCollector
from agent_review.collectors.golangci_lint import GolangciLintCollector
from agent_review.collectors.luacheck import LuacheckCollector
from agent_review.collectors.registry import CollectorRegistry
from agent_review.collectors.roslyn import RoslynCollector
from agent_review.collectors.secrets import SecretsCollector
from agent_review.collectors.semgrep import SemgrepCollector
from agent_review.collectors.sonar import SonarCollector
from agent_review.collectors.spotbugs import SpotBugsCollector
from agent_review.crypto import decrypt_value
from agent_review.gate import GateController, PolicyLoader
from agent_review.models import Finding
from agent_review.models.app_config import AppConfig
from agent_review.models.user_settings import UserSettings
from agent_review.normalize import FindingsDeduplicator, FindingsNormalizer
from agent_review.normalize.reachability import ReachabilityAnalyzer
from agent_review.pipeline.engine_router import EngineRouter
from agent_review.reasoning import LLMClient, PromptManager, Synthesizer

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from agent_review.collectors.base import CollectorResult
    from agent_review.config import Settings
    from agent_review.models import ReviewRun
    from agent_review.observability import RunMetrics
    from agent_review.observability.pipeline_logger import PipelineLogger
    from agent_review.reasoning.degraded import SynthesisResult
    from agent_review.schemas.classification import Classification
    from agent_review.schemas.decision import ReviewDecision
    from agent_review.schemas.finding import FindingCreate
    from agent_review.schemas.policy import PolicyConfig, ScanTrackConfig
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


_LLM_KEY_NAMES: list[str] = [
    "llm_openai_api_key",
    "llm_gemini_api_key",
    "llm_github_api_key",
    "llm_anthropic_api_key",
]


async def _resolve_api_keys(
    db: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID | None = None,
) -> dict[str, str]:
    """Resolve LLM API keys: UserSettings (per-user) → AppConfig (global) → env."""
    import json as _json

    api_keys: dict[str, str] = {}
    secret = settings.secret_key.get_secret_value()

    # Layer 1: Per-user overrides (highest priority)
    user_overrides: dict[str, str] = {}
    if user_id is not None:
        result = await db.execute(
            select(UserSettings).where(
                UserSettings.user_id == user_id,
                UserSettings.key.in_(_LLM_KEY_NAMES),
            )
        )
        for row in result.scalars().all():
            decrypted = decrypt_value(_json.loads(row.value), secret)
            if decrypted:
                user_overrides[row.key] = decrypted

    # Layer 2: Global AppConfig overrides
    result = await db.execute(select(AppConfig).where(AppConfig.key.in_(_LLM_KEY_NAMES)))
    global_overrides = {r.key: r for r in result.scalars().all()}

    # Merge in priority order: user → global → env
    for k in _LLM_KEY_NAMES:
        if k in user_overrides:
            api_keys[k] = user_overrides[k]
            continue
        override = global_overrides.get(k)
        if override is not None:
            decrypted = decrypt_value(_json.loads(override.value), secret)
            if decrypted:
                api_keys[k] = decrypted
                continue
        env_val = getattr(settings, k, None)
        if isinstance(env_val, SecretStr) and env_val.get_secret_value():
            api_keys[k] = env_val.get_secret_value()

    return api_keys


def _load_engine_tiers(policy: PolicyConfig) -> ScanTrackConfig:
    return policy.engine_tiers


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
    user_id: uuid.UUID | None = None,
    local_path: str | None = None,
    plog: PipelineLogger | None = None,
) -> AnalysisResult:
    stage_started = time.perf_counter()
    await _do_transition(db, run, "CLASSIFYING")
    if plog:
        plog.stage_start("CLASSIFYING")

    classifier = Classifier()
    classification = classifier.classify(changed_files, {})
    run.classification = classification.model_dump(mode="json")
    if hasattr(run, "detected_languages"):
        run.detected_languages = classification.detected_languages
    await db.commit()
    metrics.classification_ms = int((time.perf_counter() - stage_started) * 1000)
    if plog:
        plog.stage_end(
            "CLASSIFYING",
            change_type=classification.change_type,
            risk_level=classification.risk_level,
        )

    stage_started = time.perf_counter()
    await _do_transition(db, run, "COLLECTING")
    if plog:
        plog.stage_start("COLLECTING")

    policy_loader = PolicyLoader(settings.policy_dir)
    policy = policy_loader.load(run.repo)
    if plog:
        plog.info("COLLECTING", "Policy loaded", repo=run.repo)

    all_collectors: dict[str, AbstractCollector] = {
        "semgrep": SemgrepCollector(settings, http_client),
        "sonar": SonarCollector(settings, http_client),
        "github_ci": GitHubCICollector(),
        "secrets": SecretsCollector(),
        "gitleaks": GitleaksCollector(settings, http_client),
        "spotbugs": SpotBugsCollector(settings, http_client),
        "golangci_lint": GolangciLintCollector(settings, http_client),
        "cppcheck": CppcheckCollector(settings, http_client),
        "eslint_security": EslintSecurityCollector(settings, http_client),
        "roslyn": RoslynCollector(settings, http_client),
        "luacheck": LuacheckCollector(settings, http_client),
        "codeql": CodeQLCollector(settings, http_client),
    }

    detected_langs = set(classification.detected_languages)
    scan_track: Literal["incremental", "baseline"] = (
        "baseline" if run.run_kind.value == "baseline" else "incremental"
    )
    engine_tiers = _load_engine_tiers(policy)
    router = EngineRouter()
    selection = router.select(scan_track, detected_langs, engine_tiers)

    collectors: dict[str, AbstractCollector] = {
        name: all_collectors[name] for name in selection.collectors if name in all_collectors
    }

    if plog:
        plog.info(
            "COLLECTING",
            "Engine routing complete",
            scan_track=scan_track,
            selected_collectors=list(collectors.keys()),
            rationale=selection.rationale,
        )

    if hasattr(run, "engine_selection"):
        run.engine_selection = {
            "collectors": selection.collectors,
            "tier_breakdown": selection.tier_breakdown,
            "rationale": selection.rationale,
        }
        await db.commit()

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
    if plog:
        for cr in collector_results:
            plog.info(
                "COLLECTING",
                f"Collector {cr.collector_name}: {cr.status}",
                collector=cr.collector_name,
                status=cr.status,
                finding_count=len(cr.raw_findings),
                duration_ms=cr.duration_ms,
                error=cr.error,
            )
        plog.stage_end(
            "COLLECTING", total_raw_findings=sum(len(cr.raw_findings) for cr in collector_results)
        )

    stage_started = time.perf_counter()
    await _do_transition(db, run, "NORMALIZING")
    if plog:
        plog.stage_start("NORMALIZING")

    normalizer = FindingsNormalizer()
    raw_findings = normalizer.normalize(collector_results)
    reachability = ReachabilityAnalyzer()
    raw_findings = reachability.analyze(raw_findings)
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
    if plog:
        plog.stage_end(
            "NORMALIZING",
            raw_count=len(raw_findings),
            deduped_count=len(findings),
        )

    stage_started = time.perf_counter()
    await _do_transition(db, run, "REASONING")
    if plog:
        plog.stage_start("REASONING")

    api_keys = await _resolve_api_keys(db, settings, user_id=user_id)

    llm_client = LLMClient(settings, api_keys=api_keys)
    prompt_manager = PromptManager(settings.prompts_dir)
    synthesizer = Synthesizer(llm_client, prompt_manager, settings)
    synthesis = await synthesizer.synthesize(findings, ctx)
    metrics.reasoning_ms = int((time.perf_counter() - stage_started) * 1000)
    metrics.llm_cost_cents = synthesis.cost_cents
    metrics.is_degraded = synthesis.is_degraded

    enriched_count = 0
    if not synthesis.is_degraded and synthesis.prioritized_findings:
        fix_map: dict[str, str] = {}
        for pf in synthesis.prioritized_findings:
            if pf.suggested_fix and pf.finding_id:
                fix_map[pf.finding_id] = pf.suggested_fix
        if fix_map:
            db_findings_result = await db.execute(
                select(Finding).where(
                    Finding.review_run_id == run.id,
                    Finding.finding_id.in_(fix_map.keys()),
                )
            )
            for db_finding in db_findings_result.scalars().all():
                llm_fix = fix_map.get(db_finding.finding_id, "")
                if llm_fix:
                    db_finding.fix_recommendation = llm_fix
                    enriched_count += 1
            if enriched_count:
                await db.commit()

    if plog:
        plog.stage_end(
            "REASONING",
            model_used=synthesis.model_used,
            cost_cents=synthesis.cost_cents,
            is_degraded=synthesis.is_degraded,
            enriched_findings=enriched_count,
        )

    stage_started = time.perf_counter()
    await _do_transition(db, run, "DECIDING")
    if plog:
        plog.stage_start("DECIDING")

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
    if plog:
        plog.stage_end(
            "DECIDING",
            verdict=decision.verdict.value,
            confidence=decision.confidence,
            blocking_count=len(decision.blocking_findings),
            advisory_count=len(decision.advisory_findings),
        )

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
