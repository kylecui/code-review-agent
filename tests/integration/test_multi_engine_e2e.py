from __future__ import annotations

import hashlib
from typing import Any, cast

import httpx
import respx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_review.collectors.base import CollectorResult
from agent_review.config import Settings
from agent_review.models import Finding, ReviewRun, ReviewState, Verdict
from agent_review.pipeline.runner import PipelineRunner
from tests.factories import build_review_run


def _settings() -> Settings:
    return Settings(github_app_id=1, github_private_key=SecretStr("test-key"))


async def _create_run(session_factory: async_sessionmaker[AsyncSession]) -> ReviewRun:
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
async def test_multi_engine_pr_routes_l1_and_l2_for_python_files(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/app.py"}])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("semgrep", "success", [], 1)

    async def _empty_gitleaks(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("gitleaks", "success", [], 1)

    async def _empty_secrets(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("secrets", "success", [], 1)

    async def _empty_sonar(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("sonar", "success", [], 1)

    async def _empty_github_ci(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("github_ci", "success", [], 1)

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _empty)
    monkeypatch.setattr(
        "agent_review.collectors.gitleaks.GitleaksCollector.collect", _empty_gitleaks
    )
    monkeypatch.setattr("agent_review.collectors.secrets.SecretsCollector.collect", _empty_secrets)
    monkeypatch.setattr("agent_review.collectors.sonar.SonarCollector.collect", _empty_sonar)
    monkeypatch.setattr(
        "agent_review.collectors.github_ci.GitHubCICollector.collect", _empty_github_ci
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
    assert saved.engine_selection is not None
    assert saved.engine_selection["collectors"] == [
        "semgrep",
        "gitleaks",
        "secrets",
        "sonar",
        "github_ci",
    ]


@respx.mock
async def test_multi_engine_pr_routes_l2_for_java_files(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/App.java"}])

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

    async def _spotbugs_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("spotbugs", "success", [], 1)

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
    monkeypatch.setattr(
        "agent_review.collectors.spotbugs.SpotBugsCollector.collect", _spotbugs_empty
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.metrics is not None
    collector_metrics = cast("dict[str, Any]", saved.metrics["collector_metrics"])
    assert "spotbugs" in collector_metrics


@respx.mock
async def test_multi_engine_pr_with_mixed_languages(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(
        head_sha=run.head_sha,
        files=[
            {"filename": "src/main.py"},
            {"filename": "pkg/main.go"},
            {"filename": "web/app.js"},
        ],
    )

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

    async def _golangci_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("golangci_lint", "success", [], 1)

    async def _eslint_empty(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult("eslint_security", "success", [], 1)

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
    monkeypatch.setattr(
        "agent_review.collectors.golangci_lint.GolangciLintCollector.collect",
        _golangci_empty,
    )
    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.EslintSecurityCollector.collect",
        _eslint_empty,
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        runner = PipelineRunner(_settings(), session_factory, http_client)
        await runner.run(str(run.id))

    async with session_factory() as db:
        saved = await db.get(ReviewRun, run.id)

    assert saved is not None
    assert saved.metrics is not None
    collector_metrics = cast("dict[str, Any]", saved.metrics["collector_metrics"])
    assert set(collector_metrics.keys()) == {
        "semgrep",
        "gitleaks",
        "secrets",
        "sonar",
        "github_ci",
        "golangci_lint",
        "eslint_security",
    }


@respx.mock
async def test_multi_engine_finding_dedup_across_collectors(async_engine, monkeypatch) -> None:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    run = await _create_run(session_factory)
    _mock_common_github(head_sha=run.head_sha, files=[{"filename": "src/App.java"}])

    async def _fake_token(self, installation_id: int, http_client: httpx.AsyncClient) -> str:
        _ = self
        _ = installation_id
        _ = http_client
        return "token"

    async def _semgrep_one(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult(
            "semgrep",
            "success",
            [
                {
                    "rule_id": "RULE-1",
                    "path": "src/App.java",
                    "line": 42,
                    "severity": "WARNING",
                    "message": "duplicate finding",
                }
            ],
            1,
        )

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

    async def _spotbugs_one(self, context) -> CollectorResult:
        _ = self
        _ = context
        return CollectorResult(
            "spotbugs",
            "success",
            [
                {
                    "rule_id": "RULE-1",
                    "path": "src/App.java",
                    "line": 42,
                    "severity": "WARNING",
                    "message": "duplicate finding",
                }
            ],
            1,
        )

    def _normalize_spotbugs_with_matching_fingerprint(self, result):
        findings = self._normalize_sarif_based(result, "SpotBugs", "quality.static-analysis")
        matching_fingerprint = hashlib.sha256(b"semgrep|RULE-1|src/App.java|42").hexdigest()
        return [
            finding.model_copy(update={"fingerprint": matching_fingerprint}) for finding in findings
        ]

    monkeypatch.setattr(
        "agent_review.scm.github_auth.GitHubAppAuth.get_installation_token",
        _fake_token,
    )
    monkeypatch.setattr("agent_review.collectors.semgrep.SemgrepCollector.collect", _semgrep_one)
    monkeypatch.setattr(
        "agent_review.collectors.gitleaks.GitleaksCollector.collect", _gitleaks_empty
    )
    monkeypatch.setattr("agent_review.collectors.secrets.SecretsCollector.collect", _secrets_empty)
    monkeypatch.setattr("agent_review.collectors.sonar.SonarCollector.collect", _sonar_empty)
    monkeypatch.setattr(
        "agent_review.collectors.github_ci.GitHubCICollector.collect", _github_ci_empty
    )
    monkeypatch.setattr("agent_review.collectors.spotbugs.SpotBugsCollector.collect", _spotbugs_one)
    monkeypatch.setattr(
        "agent_review.normalize.normalizer.FindingsNormalizer._normalize_spotbugs",
        _normalize_spotbugs_with_matching_fingerprint,
    )

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
    assert sorted(findings[0].source_tools) == ["semgrep", "spotbugs"]
