from typing import TYPE_CHECKING, cast

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.github_ci import GitHubCICollector

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


class StubGitHubClient:
    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        _ = method
        _ = kwargs
        if path.endswith("/check-runs"):
            return httpx.Response(
                200,
                json={
                    "check_runs": [
                        {
                            "id": 11,
                            "name": "ci / lint",
                            "conclusion": "failure",
                            "check_suite": {"id": 1001},
                        }
                    ]
                },
            )
        if path.endswith("/check-runs/11/annotations"):
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "src/main.py",
                        "start_line": 5,
                        "end_line": 5,
                        "annotation_level": "warning",
                        "message": "lint issue",
                        "title": "E501",
                    }
                ],
            )
        if path.endswith("/actions/runs/1001/artifacts"):
            return httpx.Response(200, json={"artifacts": [{"id": 1}]})
        return httpx.Response(404)


@pytest.mark.asyncio
async def test_github_ci_parses_check_run_annotations() -> None:
    collector = GitHubCICollector()
    context = CollectorContext(
        repo="o/r",
        pr_number=9,
        head_sha="a" * 40,
        base_sha="b" * 40,
        changed_files=[],
        github_client=cast("GitHubClient", StubGitHubClient()),
    )

    result = await collector.collect(context)

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["path"] == "src/main.py"
    assert result.metadata["artifacts_count"] == 1
