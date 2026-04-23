from __future__ import annotations

import json
import uuid

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from agent_review.api.user.settings import USER_CONFIGURABLE_KEYS
from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.crypto import decrypt_value, encrypt_value
from agent_review.models import Base, User
from agent_review.models.user_settings import UserSettings


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


async def test_get_user_settings_returns_only_current_user_settings() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "owner@example.com")
        await _register(client, "other@example.com")

        session_factory = app.state.session_factory
        secret_key = app.state.settings.secret_key.get_secret_value()
        async with session_factory() as db:
            owner = (
                await db.execute(select(User).where(User.email == "owner@example.com"))
            ).scalar_one()
            other = (
                await db.execute(select(User).where(User.email == "other@example.com"))
            ).scalar_one()

            db.add(
                UserSettings(
                    id=uuid.uuid4(),
                    user_id=owner.id,
                    key="llm_classify_model",
                    value=json.dumps("gpt-4o-mini"),
                )
            )
            db.add(
                UserSettings(
                    id=uuid.uuid4(),
                    user_id=other.id,
                    key="llm_openai_api_key",
                    value=json.dumps(encrypt_value("sk-other-secret", secret_key)),
                )
            )
            await db.commit()

        await _login(client, "owner@example.com")
        response = await client.get("/api/user/settings/")

    assert response.status_code == 200
    payload = response.json()["settings"]
    assert set(payload.keys()) == USER_CONFIGURABLE_KEYS
    assert payload["llm_classify_model"]["value"] == "gpt-4o-mini"
    assert payload["llm_classify_model"]["source"] == "db"
    assert payload["llm_openai_api_key"]["value"] is None
    assert payload["llm_openai_api_key"]["source"] == "default"


async def test_put_user_settings_creates_and_updates_for_current_user() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        user = await _register(client, "owner@example.com")

        put_response = await client.put(
            "/api/user/settings/",
            json={
                "llm_classify_model": "gpt-4.1-mini",
                "llm_openai_api_key": "sk-owner-abcdef123456",
            },
        )
        assert put_response.status_code == 200

        session_factory = app.state.session_factory
        secret_key = app.state.settings.secret_key.get_secret_value()
        async with session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(UserSettings).where(
                            UserSettings.user_id == uuid.UUID(str(user["id"]))
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
            secret_row = next(row for row in rows if row.key == "llm_openai_api_key")
            decrypted = decrypt_value(json.loads(secret_row.value), secret_key)
            assert decrypted == "sk-owner-abcdef123456"

        update_response = await client.put(
            "/api/user/settings/",
            json={"llm_classify_model": "gpt-4.1"},
        )

    assert update_response.status_code == 200
    payload = update_response.json()["settings"]
    assert payload["llm_classify_model"]["value"] == "gpt-4.1"
    assert payload["llm_classify_model"]["source"] == "db"


async def test_delete_user_setting_removes_only_that_users_key() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "owner@example.com")
        await _register(client, "other@example.com")

        session_factory = app.state.session_factory
        async with session_factory() as db:
            owner = (
                await db.execute(select(User).where(User.email == "owner@example.com"))
            ).scalar_one()
            other = (
                await db.execute(select(User).where(User.email == "other@example.com"))
            ).scalar_one()

            db.add(
                UserSettings(
                    id=uuid.uuid4(),
                    user_id=owner.id,
                    key="llm_classify_model",
                    value=json.dumps("gpt-owner"),
                )
            )
            db.add(
                UserSettings(
                    id=uuid.uuid4(),
                    user_id=other.id,
                    key="llm_classify_model",
                    value=json.dumps("gpt-other"),
                )
            )
            await db.commit()

        await _login(client, "owner@example.com")
        delete_response = await client.delete("/api/user/settings/llm_classify_model")
        assert delete_response.status_code == 200

        async with session_factory() as db:
            owner_row = (
                await db.execute(
                    select(UserSettings).where(
                        UserSettings.user_id == owner.id,
                        UserSettings.key == "llm_classify_model",
                    )
                )
            ).scalar_one_or_none()
            other_row = (
                await db.execute(
                    select(UserSettings).where(
                        UserSettings.user_id == other.id,
                        UserSettings.key == "llm_classify_model",
                    )
                )
            ).scalar_one_or_none()

    assert owner_row is None
    assert other_row is not None
    assert json.loads(other_row.value) == "gpt-other"


async def test_user_settings_requires_authentication() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        response = await client.get("/api/user/settings/")

    assert response.status_code == 401


async def test_user_settings_masks_secret_values_in_response() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "owner@example.com")

        put_response = await client.put(
            "/api/user/settings/",
            json={"llm_openai_api_key": "sk-very-long-owner-secret-123456"},
        )
        assert put_response.status_code == 200

        get_response = await client.get("/api/user/settings/")

    assert get_response.status_code == 200
    masked = get_response.json()["settings"]["llm_openai_api_key"]["value"]
    assert masked is not None
    assert "****" in masked
    assert "sk-very-long-owner-secret-123456" not in masked
