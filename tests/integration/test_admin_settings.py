from __future__ import annotations

import httpx
from pydantic import SecretStr

from agent_review.api.admin.settings import OPERATIONAL_KEYS
from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base


async def _init_tables(app) -> None:
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        github_webhook_secret=SecretStr("s"),
        secret_key=SecretStr("test-secret-key"),
    )


async def _register(
    client: httpx.AsyncClient, email: str, password: str = "password123"
) -> dict[str, object]:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


async def _login(client: httpx.AsyncClient, email: str, password: str = "password123") -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


async def test_get_settings_requires_auth() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        response = await client.get("/api/admin/settings/")

    assert response.status_code == 401


async def test_get_settings_requires_superuser() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")
        await _register(client, "viewer@example.com")
        await _login(client, "viewer@example.com")

        response = await client.get("/api/admin/settings/")

    assert response.status_code == 403


async def test_get_settings_returns_defaults() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.get("/api/admin/settings/")

    assert response.status_code == 200
    payload = response.json()["settings"]
    assert set(payload.keys()) == OPERATIONAL_KEYS
    for key in OPERATIONAL_KEYS:
        assert payload[key]["source"] == "env"


async def test_put_settings_updates_value() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        put_response = await client.put(
            "/api/admin/settings/",
            json={"llm_classify_model": "gpt-4o"},
        )
        assert put_response.status_code == 200

        get_response = await client.get("/api/admin/settings/")

    assert get_response.status_code == 200
    config = get_response.json()["settings"]["llm_classify_model"]
    assert config["value"] == "gpt-4o"
    assert config["source"] == "db"


async def test_put_settings_rejects_infrastructure_key() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.put("/api/admin/settings/", json={"database_url": "x"})

    assert response.status_code == 422


async def test_put_settings_rejects_unknown_key() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.put("/api/admin/settings/", json={"nonexistent": "x"})

    assert response.status_code == 422


async def test_delete_setting_reverts_to_env() -> None:
    app = create_app(_settings())
    expected = app.state.settings.llm_classify_model

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        put_response = await client.put(
            "/api/admin/settings/",
            json={"llm_classify_model": "gpt-4o"},
        )
        assert put_response.status_code == 200

        delete_response = await client.delete("/api/admin/settings/llm_classify_model")
        assert delete_response.status_code == 200

        get_response = await client.get("/api/admin/settings/")

    assert get_response.status_code == 200
    config = get_response.json()["settings"]["llm_classify_model"]
    assert config["value"] == expected
    assert config["source"] == "env"


async def test_delete_setting_not_found() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.delete("/api/admin/settings/llm_classify_model")

    assert response.status_code == 404


async def test_delete_setting_invalid_key() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.delete("/api/admin/settings/database_url")

    assert response.status_code == 422
