from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base, Finding, ReviewRun, ReviewState, RunKind
from agent_review.models.enums import FindingConfidence, FindingDisposition, FindingSeverity

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI


@pytest.fixture
async def app() -> AsyncGenerator[FastAPI, None]:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        github_webhook_secret=SecretStr("s"),
        secret_key=SecretStr("test-secret-key"),
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        async with application.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield application


@pytest.fixture
async def client(app) -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


async def _register(
    client: httpx.AsyncClient, email: str, password: str = "password123"
) -> dict[str, object]:
    response = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


async def _login(client: httpx.AsyncClient, email: str, password: str = "password123") -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


async def _create_viewer(
    client: httpx.AsyncClient, *, bootstrap_admin: bool = True
) -> dict[str, object]:
    if bootstrap_admin:
        await _register(client, "admin@example.com")

    login_response = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200

    response = await client.post(
        "/api/admin/users/",
        json={
            "email": "viewer@example.com",
            "password": "password123",
            "is_superuser": False,
        },
    )
    assert response.status_code == 201
    await client.post("/api/auth/logout")
    await _login(client, "viewer@example.com")
    return response.json()


async def _create_scan(
    client: httpx.AsyncClient,
    session_factory,
    repo: str = "test/repo",
    state: ReviewState = ReviewState.COMPLETED,
) -> ReviewRun:
    """Create a ReviewRun directly in DB for testing."""
    _ = client
    async with session_factory() as db:
        run = ReviewRun(
            id=uuid.uuid4(),
            repo=repo,
            run_kind=RunKind.BASELINE,
            head_sha="a" * 40,
            state=state,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def test_list_scans_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/scans/")
    assert response.status_code == 401


async def test_list_scans_viewer_ok(app, client: httpx.AsyncClient) -> None:
    _ = app
    await _create_viewer(client)

    response = await client.get("/api/admin/scans/")
    assert response.status_code == 200


async def test_list_scans_pagination(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    for idx in range(25):
        await _create_scan(client, app.state.session_factory, repo=f"owner/repo-{idx}")

    page_1 = await client.get("/api/admin/scans/?page=1&page_size=20")
    assert page_1.status_code == 200
    payload_1 = page_1.json()
    assert payload_1["page"] == 1
    assert payload_1["page_size"] == 20
    assert payload_1["total"] == 25
    assert len(payload_1["items"]) == 20

    page_2 = await client.get("/api/admin/scans/?page=2&page_size=20")
    assert page_2.status_code == 200
    payload_2 = page_2.json()
    assert payload_2["page"] == 2
    assert payload_2["page_size"] == 20
    assert payload_2["total"] == 25
    assert len(payload_2["items"]) == 5


async def test_list_scans_filter_by_repo(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    await _create_scan(client, app.state.session_factory, repo="owner/a")
    await _create_scan(client, app.state.session_factory, repo="owner/b")
    await _create_scan(client, app.state.session_factory, repo="owner/a")

    response = await client.get("/api/admin/scans/?repo=owner/a")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert {item["repo"] for item in payload["items"]} == {"owner/a"}


async def test_list_scans_filter_by_state(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    await _create_scan(client, app.state.session_factory, state=ReviewState.PENDING)
    await _create_scan(client, app.state.session_factory, state=ReviewState.COMPLETED)
    await _create_scan(client, app.state.session_factory, state=ReviewState.PENDING)

    response = await client.get(f"/api/admin/scans/?state={ReviewState.PENDING.value}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert {item["state"] for item in payload["items"]} == {ReviewState.PENDING.value}


async def test_get_scan_detail(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    run = await _create_scan(client, app.state.session_factory)

    async with app.state.session_factory() as db:
        db.add(
            Finding(
                id=uuid.uuid4(),
                review_run_id=run.id,
                finding_id="F-001",
                category="security.test",
                severity=FindingSeverity.HIGH,
                confidence=FindingConfidence.HIGH,
                blocking=True,
                file_path="src/app.py",
                line_start=10,
                line_end=10,
                source_tools=["semgrep"],
                rule_id="rule-1",
                title="Test Finding",
                evidence=["evidence"],
                impact="impact",
                fix_recommendation="fix",
                test_recommendation="test",
                fingerprint="fingerprint-1",
                disposition=FindingDisposition.NEW,
            )
        )
        await db.commit()

    response = await client.get(f"/api/admin/scans/{run.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scan"]["id"] == str(run.id)
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["review_run_id"] == str(run.id)


async def test_get_scan_not_found(client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    response = await client.get(f"/api/admin/scans/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_trigger_scan_superuser(client: httpx.AsyncClient) -> None:
    from unittest.mock import AsyncMock, patch

    await _register(client, "admin@example.com")

    with (
        patch(
            "agent_review.scm.github_client.GitHubClient.get_default_branch",
            new_callable=AsyncMock,
            return_value="main",
        ),
        patch(
            "agent_review.scm.github_client.GitHubClient.get_branch_sha",
            new_callable=AsyncMock,
            return_value="a" * 40,
        ),
        patch("agent_review.scm.github_auth.GitHubAppAuth"),
    ):
        response = await client.post(
            "/api/admin/scans/trigger",
            json={"repo": "owner/repo", "installation_id": 123},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["repo"] == "owner/repo"
    assert payload["installation_id"] == 123
    assert payload["run_kind"] == RunKind.BASELINE.value
    assert payload["state"] == ReviewState.PENDING.value


async def test_trigger_scan_viewer_forbidden(client: httpx.AsyncClient) -> None:
    await _create_viewer(client)
    response = await client.post(
        "/api/admin/scans/trigger",
        json={"repo": "owner/repo", "installation_id": 123},
    )
    assert response.status_code == 403


async def test_cancel_scan(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    run = await _create_scan(client, app.state.session_factory, state=ReviewState.PENDING)

    response = await client.post(f"/api/admin/scans/{run.id}/cancel")
    assert response.status_code == 200
    assert response.json()["state"] in {ReviewState.SUPERSEDED.value, ReviewState.FAILED.value}


async def test_cancel_terminal_scan(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    run = await _create_scan(client, app.state.session_factory, state=ReviewState.COMPLETED)

    response = await client.post(f"/api/admin/scans/{run.id}/cancel")
    assert response.status_code == 400


async def test_delete_scan_superuser(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    run = await _create_scan(client, app.state.session_factory)

    async with app.state.session_factory() as db:
        db.add(
            Finding(
                id=uuid.uuid4(),
                review_run_id=run.id,
                finding_id="F-002",
                category="security.test",
                severity=FindingSeverity.MEDIUM,
                confidence=FindingConfidence.MEDIUM,
                blocking=False,
                file_path="src/main.py",
                line_start=3,
                line_end=None,
                source_tools=["semgrep"],
                rule_id=None,
                title="Delete me",
                evidence=["evidence"],
                impact="impact",
                fix_recommendation="fix",
                test_recommendation=None,
                fingerprint="fingerprint-2",
                disposition=FindingDisposition.NEW,
            )
        )
        await db.commit()

    response = await client.delete(f"/api/admin/scans/{run.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(run.id)

    async with app.state.session_factory() as db:
        deleted_run = await db.get(ReviewRun, run.id)
        findings = (
            (await db.execute(select(Finding).where(Finding.review_run_id == run.id)))
            .scalars()
            .all()
        )

    assert deleted_run is None
    assert findings == []


async def test_delete_scan_viewer_forbidden(app, client: httpx.AsyncClient) -> None:
    await _register(client, "admin@example.com")
    run = await _create_scan(client, app.state.session_factory)
    await _create_viewer(client, bootstrap_admin=False)

    response = await client.delete(f"/api/admin/scans/{run.id}")
    assert response.status_code == 403
