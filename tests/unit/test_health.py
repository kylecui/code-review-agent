import httpx

from agent_review.app import create_app
from agent_review.config import Settings


async def test_health_endpoint_ok(tmp_path) -> None:
    db_path = tmp_path / "health.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="secret",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_endpoint_ok(tmp_path) -> None:
    db_path = tmp_path / "ready.db"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret="secret",
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
