from typing import TYPE_CHECKING, cast

import httpx
import pytest
from pydantic import SecretStr

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.semgrep import SemgrepCollector
from agent_review.config import Settings

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


class StubGitHubClient:
    pass


@pytest.mark.asyncio
async def test_semgrep_parses_findings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/deployments/o/r/findings"
        return httpx.Response(
            200,
            json={
                "findings": [
                    {
                        "check_id": "python.lang.security.audit",
                        "path": "src/auth.py",
                        "start": {"line": 12},
                        "extra": {"severity": "ERROR", "message": "Issue"},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = Settings.model_validate(
            {
                "semgrep_mode": "app",
                "semgrep_app_token": SecretStr("token"),
            }
        )
        collector = SemgrepCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["rule_id"] == "python.lang.security.audit"


@pytest.mark.asyncio
async def test_semgrep_api_error_returns_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(500, json={"error": "oops"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = Settings.model_validate(
            {
                "semgrep_mode": "app",
                "semgrep_app_token": SecretStr("token"),
            }
        )
        collector = SemgrepCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "failure"
    assert "500" in (result.error or "")
