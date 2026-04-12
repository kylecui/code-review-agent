from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest

from agent_review.app import create_app
from agent_review.config import Settings


@pytest.fixture
def spa_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "index.html").write_text('<!doctype html><div id="root"></div>')
        assets = d / "assets"
        assets.mkdir()
        (assets / "index.js").write_text("console.log('app')")
        (assets / "index.css").write_text("body{}")
        yield d


@pytest.mark.asyncio
async def test_spa_serves_index_html(spa_dir: Path) -> None:
    settings = Settings(database_url="sqlite+aiosqlite://", frontend_dir=spa_dir)
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert '<div id="root">' in resp.text


@pytest.mark.asyncio
async def test_spa_catchall_returns_index(spa_dir: Path) -> None:
    settings = Settings(database_url="sqlite+aiosqlite://", frontend_dir=spa_dir)
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/admin/nonexistent")
        assert resp.status_code == 200
        assert '<div id="root">' in resp.text


@pytest.mark.asyncio
async def test_api_routes_not_intercepted_by_spa(spa_dir: Path) -> None:
    settings = Settings(database_url="sqlite+aiosqlite://", frontend_dir=spa_dir)
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"


@pytest.mark.asyncio
async def test_webhooks_not_intercepted_by_spa(spa_dir: Path) -> None:
    settings = Settings(database_url="sqlite+aiosqlite://", frontend_dir=spa_dir)
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhooks/github",
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=fake",
                "X-GitHub-Delivery": "test-delivery",
            },
            content=b"{}",
        )
        assert resp.status_code != 404


@pytest.mark.asyncio
async def test_spa_not_mounted_when_dir_missing() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        frontend_dir=Path("/nonexistent/path"),
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
