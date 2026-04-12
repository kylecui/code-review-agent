from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent_review.collectors.base import CollectorContext, CollectorResult
from agent_review.config import Settings
from agent_review.models import ReviewRun, ReviewState, RunKind, Verdict
from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.pipeline.baseline_runner import BaselineRunner
from agent_review.reasoning.degraded import SynthesisResult
from agent_review.schemas.classification import Classification
from agent_review.schemas.decision import ReviewDecision
from agent_review.schemas.finding import FindingCreate
from agent_review.schemas.policy import PolicyConfig
from tests.factories import build_review_run


def _finding() -> FindingCreate:
    return FindingCreate(
        finding_id="f-1",
        category="quality.issue",
        severity=FindingSeverity.LOW,
        confidence=FindingConfidence.HIGH,
        blocking=False,
        file_path="src/app.py",
        line_start=1,
        source_tools=["semgrep"],
        title="t",
        evidence=["e"],
        impact="i",
        fix_recommendation="f",
        fingerprint="fp-1",
    )


class FakeGitHubAppAuth:
    def __init__(self, *_args, **_kwargs):
        pass


class FakeGitHubClient:
    def __init__(self, *_args, **_kwargs):
        pass


class FakeClassifier:
    def classify(
        self, _changed_files: list[str], _pr_metadata: dict[str, object]
    ) -> Classification:
        return Classification(
            change_type="code",
            domains=["testing"],
            risk_level="low",
            profiles=["core_quality"],
            file_categories={},
        )


class FakePolicyLoader:
    def __init__(self, *_args, **_kwargs):
        pass

    def load(self, _repo: str) -> PolicyConfig:
        return PolicyConfig()


class FakeCollectorRegistry:
    def __init__(self, *_args, **_kwargs):
        pass

    async def run_collectors(
        self,
        _classification: Classification,
        _context: CollectorContext,
        _policy: PolicyConfig,
    ) -> list[CollectorResult]:
        return [
            CollectorResult(
                collector_name="semgrep",
                status="success",
                raw_findings=[],
                duration_ms=1,
            )
        ]


class FakeFindingsNormalizer:
    def normalize(self, _results: list[CollectorResult]) -> list[FindingCreate]:
        return [_finding()]


class FakeFindingsDeduplicator:
    def deduplicate(self, findings: list[FindingCreate]) -> list[FindingCreate]:
        return findings


class FakeSynthesizer:
    def __init__(self, *_args, **_kwargs):
        pass

    async def synthesize(
        self,
        _findings: list[FindingCreate],
        _context: CollectorContext,
    ) -> SynthesisResult:
        return SynthesisResult(
            prioritized_findings=[],
            summary="ok",
            overall_risk="low",
            model_used="deterministic",
            cost_cents=0.0,
            is_degraded=False,
        )


class FakeGateController:
    def evaluate(self, **_kwargs) -> ReviewDecision:
        return ReviewDecision(
            verdict=Verdict.PASS,
            confidence="low",
            blocking_findings=[],
            advisory_findings=[],
            escalation_reasons=[],
            missing_evidence=[],
            summary="ok",
        )


class RaisingGateController:
    def evaluate(self, **_kwargs) -> ReviewDecision:
        raise RuntimeError("gate boom")


async def test_baseline_runner_success(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = build_review_run(
        state=ReviewState.PENDING,
        run_kind=RunKind.BASELINE,
        pr_number=None,
        base_sha=None,
        trigger_event=None,
        delivery_id=None,
    )
    async with session_factory() as db:
        db.add(run)
        await db.commit()

    import datetime as dt

    import agent_review.pipeline.analysis as analysis_module
    import agent_review.pipeline.baseline_runner as br_module

    def _permissive_transition(self: ReviewRun, new_state: ReviewState) -> None:
        now = dt.datetime.now(dt.UTC)
        self.state = new_state
        self.updated_at = now
        if new_state in {ReviewState.COMPLETED, ReviewState.FAILED, ReviewState.SUPERSEDED}:
            self.completed_at = now

    monkeypatch.setattr(ReviewRun, "transition", _permissive_transition)
    monkeypatch.setattr(br_module, "GitHubAppAuth", FakeGitHubAppAuth)
    monkeypatch.setattr(br_module, "GitHubClient", FakeGitHubClient)
    monkeypatch.setattr(analysis_module, "Classifier", FakeClassifier)
    monkeypatch.setattr(analysis_module, "PolicyLoader", FakePolicyLoader)
    monkeypatch.setattr(analysis_module, "CollectorRegistry", FakeCollectorRegistry)
    monkeypatch.setattr(analysis_module, "FindingsNormalizer", FakeFindingsNormalizer)
    monkeypatch.setattr(analysis_module, "FindingsDeduplicator", FakeFindingsDeduplicator)
    monkeypatch.setattr(analysis_module, "Synthesizer", FakeSynthesizer)
    monkeypatch.setattr(analysis_module, "GateController", FakeGateController)

    async with httpx.AsyncClient() as http_client:
        runner = BaselineRunner(Settings(), session_factory, http_client)
        result = await runner.run(str(run.id))

    from agent_review.pipeline.analysis import AnalysisResult

    assert isinstance(result, AnalysisResult)

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.COMPLETED
    assert saved.metrics is not None


async def test_baseline_runner_failure(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = build_review_run(
        state=ReviewState.PENDING,
        run_kind=RunKind.BASELINE,
        pr_number=None,
        base_sha=None,
        trigger_event=None,
        delivery_id=None,
    )
    async with session_factory() as db:
        db.add(run)
        await db.commit()

    import agent_review.pipeline.analysis as analysis_module
    import agent_review.pipeline.baseline_runner as br_module

    monkeypatch.setattr(br_module, "GitHubAppAuth", FakeGitHubAppAuth)
    monkeypatch.setattr(br_module, "GitHubClient", FakeGitHubClient)
    monkeypatch.setattr(analysis_module, "Classifier", FakeClassifier)
    monkeypatch.setattr(analysis_module, "PolicyLoader", FakePolicyLoader)
    monkeypatch.setattr(analysis_module, "CollectorRegistry", FakeCollectorRegistry)
    monkeypatch.setattr(analysis_module, "FindingsNormalizer", FakeFindingsNormalizer)
    monkeypatch.setattr(analysis_module, "FindingsDeduplicator", FakeFindingsDeduplicator)
    monkeypatch.setattr(analysis_module, "Synthesizer", FakeSynthesizer)
    monkeypatch.setattr(analysis_module, "GateController", RaisingGateController)

    async with httpx.AsyncClient() as http_client:
        runner = BaselineRunner(Settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.FAILED
    assert saved.error is not None
    assert "gate boom" in saved.error


async def test_baseline_runner_terminal_run_noop(async_engine) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = build_review_run(
        state=ReviewState.COMPLETED,
        run_kind=RunKind.BASELINE,
        pr_number=None,
        base_sha=None,
        trigger_event=None,
        delivery_id=None,
    )
    async with session_factory() as db:
        db.add(run)
        await db.commit()

    async with httpx.AsyncClient() as http_client:
        runner = BaselineRunner(Settings(), session_factory, http_client)
        result = await runner.run(str(run.id))

    assert result is None
