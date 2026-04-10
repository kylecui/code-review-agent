from typing import TYPE_CHECKING, cast

import httpx
import pytest
from pydantic import SecretStr

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.sonar import SonarCollector
from agent_review.config import Settings

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


class StubGitHubClient:
    pass


@pytest.mark.asyncio
async def test_sonar_parses_issues() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/qualitygates/project_status"):
            return httpx.Response(200, json={"projectStatus": {"status": "OK"}})
        if request.url.path.endswith("/api/issues/search"):
            return httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "key": "ISSUE-1",
                            "rule": "python:S001",
                            "severity": "MAJOR",
                            "type": "BUG",
                            "message": "bad",
                            "component": "o/r:src/a.py",
                            "line": 8,
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = Settings.model_validate(
            {
                "sonar_host_url": "https://sonar.example.com",
                "sonar_token": SecretStr("sonar-token"),
            }
        )
        collector = SonarCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=3,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "success"
    assert result.metadata["quality_gate"] == "OK"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["key"] == "ISSUE-1"


@pytest.mark.asyncio
async def test_missing_sonar_config_returns_skipped() -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"sonar_host_url": None, "sonar_token": None})
        collector = SonarCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=3,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "skipped"
    assert result.error == "Sonar configuration missing"
