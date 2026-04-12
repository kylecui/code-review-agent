from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent_review.collectors.base import CollectorContext, CollectorResult
from agent_review.config import Settings
from agent_review.models import ReviewRun, ReviewState, Verdict
from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.pipeline.runner import PipelineRunner
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


class FakeGitHubClient:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_pr_files(self, _repo: str, _pr_number: int) -> list[dict[str, object]]:
        return [{"filename": "src/app.py"}]

    async def get_pr(self, _repo: str, _pr_number: int) -> dict[str, object]:
        return {"labels": []}

    async def create_check_run(self, **_kwargs) -> dict[str, object]:
        return {"id": 1}

    async def create_review(self, **_kwargs) -> dict[str, object]:
        return {"id": 2}


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


class FakePromptManager:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def render(self, _template_name: str, **_context: object) -> str:
        return "summary"


class RaisingGateController:
    def evaluate(self, **_kwargs) -> ReviewDecision:
        raise RuntimeError("gate boom")


async def test_pipeline_runner_success_state_transitions(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = build_review_run(state=ReviewState.PENDING)
    async with session_factory() as db:
        db.add(run)
        await db.commit()

    import agent_review.pipeline.runner as runner_module

    transitions: list[ReviewState] = []
    original_transition = ReviewRun.transition

    def _record_transition(self: ReviewRun, new_state: ReviewState) -> None:
        transitions.append(new_state)
        original_transition(self, new_state)

    monkeypatch.setattr(runner_module, "GitHubClient", FakeGitHubClient)
    monkeypatch.setattr(runner_module, "Classifier", FakeClassifier)
    monkeypatch.setattr(runner_module, "PolicyLoader", FakePolicyLoader)
    monkeypatch.setattr(runner_module, "CollectorRegistry", FakeCollectorRegistry)
    monkeypatch.setattr(runner_module, "FindingsNormalizer", FakeFindingsNormalizer)
    monkeypatch.setattr(runner_module, "FindingsDeduplicator", FakeFindingsDeduplicator)
    monkeypatch.setattr(runner_module, "Synthesizer", FakeSynthesizer)
    monkeypatch.setattr(runner_module, "GateController", FakeGateController)
    monkeypatch.setattr(runner_module, "PromptManager", FakePromptManager)
    monkeypatch.setattr(ReviewRun, "transition", _record_transition)

    async with httpx.AsyncClient() as http_client:
        runner = PipelineRunner(Settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.COMPLETED
    assert saved.classification is not None
    assert saved.decision is not None
    assert saved.metrics is not None
    assert transitions == [
        ReviewState.CLASSIFYING,
        ReviewState.COLLECTING,
        ReviewState.NORMALIZING,
        ReviewState.REASONING,
        ReviewState.DECIDING,
        ReviewState.PUBLISHING,
        ReviewState.COMPLETED,
    ]


async def test_pipeline_runner_failure_transitions_to_failed(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = build_review_run(state=ReviewState.PENDING)
    async with session_factory() as db:
        db.add(run)
        await db.commit()

    import agent_review.pipeline.runner as runner_module

    monkeypatch.setattr(runner_module, "GitHubClient", FakeGitHubClient)
    monkeypatch.setattr(runner_module, "Classifier", FakeClassifier)
    monkeypatch.setattr(runner_module, "PolicyLoader", FakePolicyLoader)
    monkeypatch.setattr(runner_module, "CollectorRegistry", FakeCollectorRegistry)
    monkeypatch.setattr(runner_module, "FindingsNormalizer", FakeFindingsNormalizer)
    monkeypatch.setattr(runner_module, "FindingsDeduplicator", FakeFindingsDeduplicator)
    monkeypatch.setattr(runner_module, "Synthesizer", FakeSynthesizer)
    monkeypatch.setattr(runner_module, "GateController", RaisingGateController)
    monkeypatch.setattr(runner_module, "PromptManager", FakePromptManager)

    async with httpx.AsyncClient() as http_client:
        runner = PipelineRunner(Settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.FAILED
    assert saved.error is not None
    assert "gate boom" in saved.error
