from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import respx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_review.collectors.base import CollectorResult
from agent_review.config import Settings
from agent_review.models import Finding, ReviewRun, ReviewState, RunKind
from agent_review.pipeline.runner import PipelineRunner
from tests.factories import build_review_run


def _settings() -> Settings:
    return Settings(github_app_id=1, github_private_key=SecretStr("test-key"))


async def _create_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_kind: RunKind,
) -> ReviewRun:
    run = build_review_run(
        repo="owner/repo",
        pr_number=7,
        installation_id=12345,
        state=ReviewState.PENDING,
        run_kind=run_kind,
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
async def test_baseline_scan_enables_l3_codeql(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory, run_kind=RunKind.BASELINE)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/app.py"}])

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

    async def _secrets_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("secrets", "success", [], 1)

    async def _sonar_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("sonar", "success", [], 1)

    async def _codeql_one(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult(
            "codeql",
            "success",
            [
                {
                    "rule_id": "py/sql-injection",
                    "path": "src/app.py",
                    "line": 12,
                    "severity": "ERROR",
                    "message": "Possible SQL injection",
                    "precision": "high",
                    "category": "security",
                }
            ],
            1,
        )

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_empty)
    monkeypatch.setattr(
        "agent_review.collectors.gitleaks.GitleaksCollector.collect", _gitleaks_empty
    )
    monkeypatch.setattr("agent_review.collectors.secrets.SecretsCollector.collect", _secrets_empty)
    monkeypatch.setattr("agent_review.collectors.sonar.SonarCollector.collect", _sonar_empty)
    monkeypatch.setattr("agent_review.collectors.codeql.CodeQLCollector.collect", _codeql_one)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        findings = (
            (await db.execute(select(Finding).where(Finding.review_run_id == run.id)))
            .scalars()
            .all()
        )

    assert len(findings) == 1


@respx.mock
async def test_incremental_scan_skips_codeql(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory, run_kind=RunKind.PR)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/app.py"}])

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

    async def _secrets_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("secrets", "success", [], 1)

    async def _sonar_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("sonar", "success", [], 1)

    async def _github_ci_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("github_ci", "success", [], 1)

    codeql_collect = AsyncMock(return_value=CollectorResult("codeql", "success", [], 1))

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_empty)
    monkeypatch.setattr(
        "agent_review.collectors.gitleaks.GitleaksCollector.collect", _gitleaks_empty
    )
    monkeypatch.setattr("agent_review.collectors.secrets.SecretsCollector.collect", _secrets_empty)
    monkeypatch.setattr("agent_review.collectors.sonar.SonarCollector.collect", _sonar_empty)
    monkeypatch.setattr(
        "agent_review.collectors.github_ci.GitHubCICollector.collect", _github_ci_empty
    )
    monkeypatch.setattr("agent_review.collectors.codeql.CodeQLCollector.collect", codeql_collect)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.metrics is not None
    collector_metrics = cast("dict[str, Any]", saved.metrics["collector_metrics"])
    assert "codeql" not in collector_metrics
    assert codeql_collect.await_count == 0
