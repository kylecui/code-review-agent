import httpx
import pytest
import respx

from agent_review.scm.github_client import GitHubClient


class StubAuth:
    async def get_installation_token(
        self, installation_id: int, http_client: httpx.AsyncClient
    ) -> str:
        _ = installation_id
        _ = http_client
        return "inst-token"


@pytest.mark.asyncio
@respx.mock
async def test_create_check_run() -> None:
    route = respx.post("https://api.github.com/repos/o/r/check-runs").mock(
        return_value=httpx.Response(201, json={"id": 10, "status": "in_progress"})
    )
    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        result = await client.create_check_run("o/r", "a" * 40, "agent-review", "run-1")

    assert route.called
    assert result["id"] == 10


@pytest.mark.asyncio
@respx.mock
async def test_create_review() -> None:
    route = respx.post("https://api.github.com/repos/o/r/pulls/7/reviews").mock(
        return_value=httpx.Response(200, json={"id": 99, "event": "COMMENT"})
    )
    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        result = await client.create_review("o/r", 7, "a" * 40, "COMMENT", "body")

    assert route.called
    assert result["id"] == 99


@pytest.mark.asyncio
@respx.mock
async def test_upsert_comment_create_path() -> None:
    list_route = respx.get("https://api.github.com/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "body": "other comment"}])
    )
    create_route = respx.post("https://api.github.com/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(201, json={"id": 2, "body": "new body"})
    )

    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        result = await client.upsert_comment("o/r", 7, "SENTINEL", "new body")

    assert list_route.called
    assert create_route.called
    assert result["id"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_upsert_comment_update_path() -> None:
    list_route = respx.get("https://api.github.com/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 44, "body": "prefix SENTINEL suffix"}],
        )
    )
    patch_route = respx.patch("https://api.github.com/repos/o/r/issues/comments/44").mock(
        return_value=httpx.Response(200, json={"id": 44, "body": "updated"})
    )

    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        result = await client.upsert_comment("o/r", 7, "SENTINEL", "updated")

    assert list_route.called
    assert patch_route.called
    assert result["id"] == 44


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_retry() -> None:
    route = respx.post("https://api.github.com/repos/o/r/check-runs")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(201, json={"id": 11}),
    ]

    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        result = await client.create_check_run("o/r", "a" * 40, "agent-review", "run-1")

    assert result["id"] == 11
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_pr_and_files() -> None:
    pr_route = respx.get("https://api.github.com/repos/o/r/pulls/7").mock(
        return_value=httpx.Response(200, json={"number": 7, "head": {"sha": "a" * 40}})
    )
    files_route = respx.get("https://api.github.com/repos/o/r/pulls/7/files").mock(
        return_value=httpx.Response(200, json=[{"filename": "src/a.py"}])
    )

    async with httpx.AsyncClient() as http_client:
        client = GitHubClient(http_client=http_client, auth=StubAuth(), installation_id=1)
        pr = await client.get_pr("o/r", 7)
        files = await client.get_pr_files("o/r", 7)

    assert pr_route.called
    assert files_route.called
    assert pr["number"] == 7
    assert files[0]["filename"] == "src/a.py"
