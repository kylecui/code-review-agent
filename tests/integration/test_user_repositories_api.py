from __future__ import annotations

import json
import uuid

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.crypto import decrypt_value, encrypt_value
from agent_review.models import Base, User
from agent_review.models.user_repository import UserRepository


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


async def test_list_repositories_returns_only_current_users_repos() -> None:
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
                UserRepository(
                    id=uuid.uuid4(),
                    user_id=owner.id,
                    repo_url="https://github.com/owner/alpha",
                    repo_name="alpha",
                    provider="github",
                    auth_token=json.dumps(encrypt_value("owner-token-123", secret_key)),
                    default_branch="main",
                )
            )
            db.add(
                UserRepository(
                    id=uuid.uuid4(),
                    user_id=other.id,
                    repo_url="https://github.com/other/beta",
                    repo_name="beta",
                    provider="github",
                    auth_token=json.dumps(encrypt_value("other-token-123", secret_key)),
                    default_branch="main",
                )
            )
            await db.commit()

        await _login(client, "owner@example.com")
        response = await client.get("/api/user/repositories/")

    assert response.status_code == 200
    repos = response.json()["repositories"]
    assert len(repos) == 1
    assert repos[0]["repo_name"] == "alpha"
    assert repos[0]["repo_url"] == "https://github.com/owner/alpha"
    assert "****" in (repos[0]["auth_token"] or "")


async def test_post_repositories_creates_repo_owned_by_current_user() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        user = await _register(client, "owner@example.com")

        response = await client.post(
            "/api/user/repositories/",
            json={
                "repo_url": "https://github.com/owner/new-repo",
                "repo_name": "new-repo",
                "provider": "github",
                "auth_token": "new-owner-token-xyz",
                "default_branch": "develop",
            },
        )

        session_factory = app.state.session_factory
        secret_key = app.state.settings.secret_key.get_secret_value()
        async with session_factory() as db:
            row = (
                await db.execute(
                    select(UserRepository).where(
                        UserRepository.user_id == uuid.UUID(str(user["id"])),
                        UserRepository.repo_url == "https://github.com/owner/new-repo",
                    )
                )
            ).scalar_one_or_none()

    assert response.status_code == 201
    assert row is not None
    assert row.user_id == uuid.UUID(str(user["id"]))
    assert row.auth_token is not None
    assert decrypt_value(json.loads(row.auth_token), secret_key) == "new-owner-token-xyz"


async def test_put_repository_updates_only_if_owned_by_current_user() -> None:
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
            owned_repo = UserRepository(
                id=uuid.uuid4(),
                user_id=owner.id,
                repo_url="https://github.com/owner/updatable",
                repo_name="updatable",
                provider="github",
                auth_token=json.dumps(encrypt_value("old-token", secret_key)),
                default_branch="main",
            )
            db.add(owned_repo)
            await db.commit()
            await db.refresh(owned_repo)
            repo_id = owned_repo.id

        await _login(client, "owner@example.com")
        response = await client.put(
            f"/api/user/repositories/{repo_id}",
            json={
                "repo_name": "updated-name",
                "default_branch": "develop",
                "auth_token": "****",
                "scan_enabled": False,
            },
        )

        async with session_factory() as db:
            updated = await db.get(UserRepository, repo_id)

    assert response.status_code == 200
    assert updated is not None
    assert updated.repo_name == "updated-name"
    assert updated.default_branch == "develop"
    assert updated.scan_enabled is False
    assert updated.auth_token is not None
    assert decrypt_value(json.loads(updated.auth_token), secret_key) == "old-token"


async def test_delete_repository_deletes_only_if_owned_by_current_user() -> None:
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

            owner_repo = UserRepository(
                id=uuid.uuid4(),
                user_id=owner.id,
                repo_url="https://github.com/owner/delete-me",
                repo_name="delete-me",
                provider="github",
                default_branch="main",
            )
            other_repo = UserRepository(
                id=uuid.uuid4(),
                user_id=other.id,
                repo_url="https://github.com/other/keep-me",
                repo_name="keep-me",
                provider="github",
                default_branch="main",
            )
            db.add(owner_repo)
            db.add(other_repo)
            await db.commit()
            await db.refresh(owner_repo)
            await db.refresh(other_repo)
            owner_repo_id = owner_repo.id
            other_repo_id = other_repo.id

        await _login(client, "owner@example.com")
        response = await client.delete(f"/api/user/repositories/{owner_repo_id}")

        async with session_factory() as db:
            deleted_owner = await db.get(UserRepository, owner_repo_id)
            remaining_other = await db.get(UserRepository, other_repo_id)

    assert response.status_code == 200
    assert deleted_owner is None
    assert remaining_other is not None


async def test_cross_user_repository_access_returns_404() -> None:
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
            owner_repo = UserRepository(
                id=uuid.uuid4(),
                user_id=owner.id,
                repo_url="https://github.com/owner/private-repo",
                repo_name="private-repo",
                provider="github",
                default_branch="main",
            )
            db.add(owner_repo)
            await db.commit()
            await db.refresh(owner_repo)
            owner_repo_id = owner_repo.id

        await _login(client, "other@example.com")
        get_response = await client.get(f"/api/user/repositories/{owner_repo_id}")
        put_response = await client.put(
            f"/api/user/repositories/{owner_repo_id}",
            json={"repo_name": "hijack"},
        )
        delete_response = await client.delete(f"/api/user/repositories/{owner_repo_id}")

    assert get_response.status_code == 404
    assert put_response.status_code == 404
    assert delete_response.status_code == 404


async def test_repository_test_endpoint_returns_stub_response() -> None:
    app = create_app(_settings())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "owner@example.com")

        create_response = await client.post(
            "/api/user/repositories/",
            json={
                "repo_url": "https://github.com/owner/test-endpoint",
                "repo_name": "test-endpoint",
            },
        )
        assert create_response.status_code == 201
        repo_id = create_response.json()["id"]

        test_response = await client.post(f"/api/user/repositories/{repo_id}/test")

    assert test_response.status_code == 200
    assert test_response.json() == {
        "status": "ok",
        "message": "Connection test not yet implemented",
    }
