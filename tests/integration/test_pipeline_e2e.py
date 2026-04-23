from __future__ import annotations

import httpx
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent_review.collectors.base import CollectorResult
from agent_review.config import Settings
from agent_review.models import ReviewRun, ReviewState, Verdict
from agent_review.pipeline.runner import PipelineRunner
from tests.factories import build_review_run


def _settings() -> Settings:
    return Settings(github_app_id=1, github_private_key="test-key")


async def _create_run(session_factory: async_sessionmaker) -> ReviewRun:
    run = build_review_run(
        repo="owner/repo",
        pr_number=7,
        installation_id=12345,
        state=ReviewState.PENDING,
    )
    async with session_factory() as db:
        db.add(run)
        await db.commit()
    return run


def _mock_common_github(
    *,
    head_sha: str,
    files: list[dict[str, object]],
    labels: list[dict[str, object]] | None = None,
) -> None:
    respx.get("https://api.github.com/repos/owner/repo/pulls/7/files").mock(
        return_value=httpx.Response(200, json=files)
    )
    respx.get("https://api.github.com/repos/owner/repo/pulls/7").mock(
        return_value=httpx.Response(200, json={"labels": labels or []})
    )
    respx.get(f"https://api.github.com/repos/owner/repo/commits/{head_sha}/check-runs").mock(
        return_value=httpx.Response(200, json={"check_runs": []})
    )
    respx.get("https://api.github.com/repos/owner/repo/secret-scanning/alerts").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post("https://api.github.com/repos/owner/repo/check-runs").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )
    respx.post("https://api.github.com/repos/owner/repo/pulls/7/reviews").mock(
        return_value=httpx.Response(200, json={"id": 2})
    )


@respx.mock
async def test_pipeline_pass_no_findings(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _semgrep_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("semgrep", "success", [], 1)

    async def _gitleaks_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("gitleaks", "success", [], 1)

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_empty)
    monkeypatch.setattr(
        "agent_review.collectors.gitleaks.GitleaksCollector.collect", _gitleaks_empty
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.COMPLETED
    assert saved.decision is not None
    assert saved.decision["verdict"] == Verdict.PASS.value


@respx.mock
async def test_pipeline_block_critical_finding(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "auth/service.py"}])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _semgrep_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("semgrep", "success", [], 1)

    async def _sonar_critical(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult(
            collector_name="sonar",
            status="success",
            raw_findings=[
                {
                    "key": "k1",
                    "rule": "r1",
                    "severity": "BLOCKER",
                    "type": "VULNERABILITY",
                    "message": "critical issue",
                    "component": "auth/service.py",
                    "line": 10,
                }
            ],
            duration_ms=1,
        )

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_empty)
    monkeypatch.setattr("agent_review.collectors.sonar.SonarCollector.collect", _sonar_critical)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.COMPLETED
    assert saved.decision is not None
    assert saved.decision["verdict"] == Verdict.BLOCK.value


@respx.mock
async def test_pipeline_degraded_synthesis(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/big.py"}])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _semgrep_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("semgrep", "success", [], 1)

    async def _secrets_many(self, context) -> CollectorResult:
        _ = self
        _ = context
        raw_findings = [
            {
                "number": i,
                "state": "open",
                "secret_type": "api_key",
                "html_url": f"https://example.test/{i}",
                "created_at": "2026-01-01T00:00:00Z",
            }
            for i in range(1, 2002)
        ]
        return CollectorResult("secrets", "success", raw_findings, 1)

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_empty)
    monkeypatch.setattr("agent_review.collectors.secrets.SecretsCollector.collect", _secrets_many)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.COMPLETED
    assert saved.metrics is not None
    assert saved.metrics["is_degraded"] is True


@respx.mock
async def test_pipeline_superseded(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/app.py"}])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _supersede_mid_run(self, repo: str, pr_number: int) -> list[dict[str, object]]:
        _ = self
        _ = repo
        _ = pr_number
        async with session_factory() as db:
            run_in_db = await db.get(ReviewRun, run.id)
            assert run_in_db is not None
            run_in_db.transition(ReviewState.SUPERSEDED)
            await db.commit()
        return [{"filename": "src/app.py"}]

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr(
        "agent_review.scm.github_client.GitHubClient.get_pr_files",
        _supersede_mid_run,
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.state == ReviewState.SUPERSEDED
    assert saved.decision is None
    assert saved.metrics is None
