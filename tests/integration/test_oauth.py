from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import func, select

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base, User


async def _init_tables(app) -> None:
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _settings(db_path: str) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        github_webhook_secret="s",
        secret_key="test-secret-key",
        github_oauth_client_id="client-id",
        github_oauth_client_secret="client-secret",
        oauth_redirect_uri="http://test/api/auth/github/callback",
    )


@respx.mock
async def test_github_login_redirects_with_expected_params(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "oauth_login.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        response = await client.get("/api/auth/github/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "github.com"
    assert parsed.path == "/login/oauth/authorize"
    assert query["client_id"][0] == "client-id"
    assert query["redirect_uri"][0] == "http://test/api/auth/github/callback"
    assert "state" in query


@respx.mock
async def test_github_callback_creates_user_and_sets_cookie(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "oauth_create.db")))

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "oauth-token"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(
            200,
            json={"id": 12345, "login": "octocat", "email": "octocat@example.com", "name": "Octo"},
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)

        login = await client.get("/api/auth/github/login", follow_redirects=False)
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        callback = await client.get(
            f"/api/auth/github/callback?code=test-code&state={state}",
            follow_redirects=False,
        )

        async with app.state.session_factory() as db:
            count = await db.execute(select(func.count()).select_from(User))
            user_count = count.scalar_one()

    assert callback.status_code in (302, 307)
    assert callback.headers["location"] == "/"
    assert callback.cookies.get("access_token")
    assert user_count == 1


@respx.mock
async def test_existing_github_user_logs_in_without_duplicate(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "oauth_existing.db")))

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "oauth-token"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 54321,
                "login": "existing",
                "email": "existing@example.com",
                "name": "Existing",
            },
        )
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)

        login_1 = await client.get("/api/auth/github/login", follow_redirects=False)
        state_1 = parse_qs(urlparse(login_1.headers["location"]).query)["state"][0]
        callback_1 = await client.get(
            f"/api/auth/github/callback?code=code-1&state={state_1}",
            follow_redirects=False,
        )

        login_2 = await client.get("/api/auth/github/login", follow_redirects=False)
        state_2 = parse_qs(urlparse(login_2.headers["location"]).query)["state"][0]
        callback_2 = await client.get(
            f"/api/auth/github/callback?code=code-2&state={state_2}",
            follow_redirects=False,
        )

        async with app.state.session_factory() as db:
            count = await db.execute(select(func.count()).select_from(User))
            user_count = count.scalar_one()

    assert callback_1.status_code in (302, 307)
    assert callback_2.status_code in (302, 307)
    assert user_count == 1
