from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base


async def _init_tables(app) -> None:
    engine = app.state.engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _app_settings(db_path: str) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        github_webhook_secret="test-secret",
        secret_key="test-secret-key",
        access_token_expire_minutes=60,
    )


async def test_register_me_logout_login_flow(tmp_path) -> None:
    app = create_app(_app_settings(str(tmp_path / "auth_flow.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)

        register = await client.post(
            "/api/auth/register",
            json={"email": "admin@example.com", "password": "password123", "full_name": "Admin"},
        )
        assert register.status_code == 200
        assert register.cookies.get("access_token")
        assert register.json()["is_superuser"] is True

        me_1 = await client.get("/api/auth/me")
        assert me_1.status_code == 200
        assert me_1.json()["email"] == "admin@example.com"

        logout = await client.post("/api/auth/logout")
        assert logout.status_code == 200

        me_2 = await client.get("/api/auth/me")
        assert me_2.status_code == 401

        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "password123"},
        )
        assert login.status_code == 200
        assert login.cookies.get("access_token")

        me_3 = await client.get("/api/auth/me")
        assert me_3.status_code == 200
        assert me_3.json()["email"] == "admin@example.com"


async def test_wrong_password_returns_401(tmp_path) -> None:
    app = create_app(_app_settings(str(tmp_path / "auth_wrong_password.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "password123"},
        )
        response = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
        )
    assert response.status_code == 401


async def test_duplicate_email_returns_409(tmp_path) -> None:
    app = create_app(_app_settings(str(tmp_path / "auth_duplicate.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        first = await client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "password123"},
        )
        second = await client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "password123"},
        )
    assert first.status_code == 200
    assert second.status_code == 409


async def test_first_user_superuser_second_not(tmp_path) -> None:
    app = create_app(_app_settings(str(tmp_path / "auth_bootstrap.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        first = await client.post(
            "/api/auth/register",
            json={"email": "first@example.com", "password": "password123"},
        )
        second = await client.post(
            "/api/auth/register",
            json={"email": "second@example.com", "password": "password123"},
        )
    assert first.status_code == 200
    assert first.json()["is_superuser"] is True
    assert second.status_code == 200
    assert second.json()["is_superuser"] is False


async def test_webhook_github_not_protected_by_auth(tmp_path) -> None:
    app = create_app(_app_settings(str(tmp_path / "auth_webhook.db")))

    payload = {
        "action": "opened",
        "sender": {"type": "User"},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 1},
        "pull_request": {
            "number": 1,
            "draft": False,
            "head": {"sha": "a" * 40},
            "base": {"sha": "b" * 40},
        },
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        response = await client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": str(uuid.uuid4()),
            },
        )

    assert response.status_code != 401
