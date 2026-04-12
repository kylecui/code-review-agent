from __future__ import annotations

import uuid

import httpx

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base, ReviewRun, RunKind


async def _init_tables(app) -> None:
    engine = app.state.engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_app(tmp_path, name: str):
    db_path = tmp_path / f"web_{name}.db"
    return create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="s",
        )
    )


async def test_scan_list_empty(tmp_path) -> None:
    app = await _create_app(tmp_path, "list_empty")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)
        response = await client.get("/ui/scans")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "No scans yet" in response.text


async def test_scan_list_with_runs(tmp_path) -> None:
    app = await _create_app(tmp_path, "list_runs")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)

        run = ReviewRun(
            id=uuid.uuid4(),
            repo="owner/repo",
            run_kind=RunKind.BASELINE,
            pr_number=None,
            head_sha="a" * 40,
            base_sha=None,
            installation_id=123,
            trigger_event=None,
            delivery_id=None,
        )
        async with app.state.session_factory() as db:
            db.add(run)
            await db.commit()

        response = await client.get("/ui/scans")

    assert response.status_code == 200
    assert "owner/repo" in response.text
    assert "baseline" in response.text


async def test_scan_detail_found(tmp_path) -> None:
    app = await _create_app(tmp_path, "detail_found")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)

        run_id = uuid.uuid4()
        run = ReviewRun(
            id=run_id,
            repo="owner/repo",
            run_kind=RunKind.BASELINE,
            pr_number=None,
            head_sha="a" * 40,
            base_sha=None,
            installation_id=123,
            trigger_event=None,
            delivery_id=None,
        )
        async with app.state.session_factory() as db:
            db.add(run)
            await db.commit()

        response = await client.get(f"/ui/scans/{run_id}")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "owner/repo" in response.text
    assert str(run_id) in response.text


async def test_scan_detail_not_found(tmp_path) -> None:
    app = await _create_app(tmp_path, "detail_404")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)
        response = await client.get(f"/ui/scans/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_scan_detail_invalid_uuid(tmp_path) -> None:
    app = await _create_app(tmp_path, "detail_bad")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get("/ui/scans/not-a-uuid")

    assert response.status_code == 400


async def test_scan_detail_with_decision(tmp_path) -> None:
    app = await _create_app(tmp_path, "detail_decision")

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        await _init_tables(app)

        run_id = uuid.uuid4()
        run = ReviewRun(
            id=run_id,
            repo="owner/repo",
            run_kind=RunKind.BASELINE,
            pr_number=None,
            head_sha="a" * 40,
            base_sha=None,
            installation_id=123,
            trigger_event=None,
            delivery_id=None,
            decision={
                "verdict": "warn",
                "confidence": "high",
                "blocking_findings": [],
                "advisory_findings": ["f-1"],
                "escalation_reasons": [],
                "missing_evidence": [],
                "summary": "advisory only",
            },
        )
        async with app.state.session_factory() as db:
            db.add(run)
            await db.commit()

        response = await client.get(f"/ui/scans/{run_id}")

    assert response.status_code == 200
    assert "warn" in response.text
    assert "advisory only" in response.text
