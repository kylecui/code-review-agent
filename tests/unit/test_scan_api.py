from __future__ import annotations

import uuid

import httpx

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base


async def _init_tables(app) -> None:
    engine = app.state.engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_create_scan_returns_202(tmp_path, monkeypatch) -> None:
    import agent_review.api.scan as scan_module

    fake_sha = "a" * 40

    async def _fake_resolve_head_sha(_github, _repo, _ref, _branch):
        return fake_sha

    async def _fake_run_baseline(_request, _run_id):
        pass

    monkeypatch.setattr(scan_module, "_resolve_head_sha", _fake_resolve_head_sha)
    monkeypatch.setattr(scan_module, "_run_baseline", _fake_run_baseline)

    db_path = tmp_path / "scan_202.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="s",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)
        response = await client.post(
            "/api/scan",
            json={"repo": "owner/repo", "installation_id": 123},
        )

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    assert "status" in body


async def test_create_scan_missing_installation_id_returns_400(tmp_path, monkeypatch) -> None:
    import agent_review.api.scan as scan_module

    async def _fake_resolve_head_sha(_github, _repo, _ref, _branch):
        return "a" * 40

    async def _fake_run_baseline(_request, _run_id):
        pass

    monkeypatch.setattr(scan_module, "_resolve_head_sha", _fake_resolve_head_sha)
    monkeypatch.setattr(scan_module, "_run_baseline", _fake_run_baseline)

    db_path = tmp_path / "scan_400.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="s",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)
        response = await client.post(
            "/api/scan",
            json={"repo": "owner/repo"},
        )

    assert response.status_code == 400


async def test_get_scan_status_not_found(tmp_path) -> None:
    db_path = tmp_path / "scan_404.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="s",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)
        response = await client.get(f"/api/scan/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_get_scan_status_invalid_uuid(tmp_path) -> None:
    db_path = tmp_path / "scan_bad.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="s",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get("/api/scan/not-a-uuid")

    assert response.status_code == 400
