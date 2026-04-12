"""Integration tests for CORS middleware configuration."""

from __future__ import annotations

import httpx
import pytest

from agent_review.app import create_app
from agent_review.config import Settings


@pytest.mark.asyncio
async def test_cors_headers_when_configured() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.options(
            "/api/admin/scans/",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-credentials" in resp.headers


@pytest.mark.asyncio
async def test_cors_headers_on_regular_request() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_no_cors_when_empty() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        cors_origins=[],
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers


@pytest.mark.asyncio
async def test_cors_does_not_break_webhooks() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Webhook should still respond (will be 400/422 due to missing body, but NOT 404)
        resp = await client.post(
            "/webhooks/github",
            headers={
                "Origin": "http://localhost:5173",
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=fake",
                "X-GitHub-Delivery": "test-delivery",
            },
            content=b"{}",
        )
        # Any status except 404 proves the route is reachable
        assert resp.status_code != 404
