from __future__ import annotations

import httpx

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base


async def _init_tables(app) -> None:
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _settings(db_path: str) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        github_webhook_secret="s",
        secret_key="test-secret-key",
    )


async def _register(client: httpx.AsyncClient, email: str, password: str = "password123") -> dict:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


async def _login(client: httpx.AsyncClient, email: str, password: str = "password123") -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


async def test_superuser_can_crud_users(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "admin_crud.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        create = await client.post(
            "/api/admin/users/",
            json={"email": "viewer@example.com", "password": "password123", "is_superuser": False},
        )
        assert create.status_code == 201
        created_user = create.json()

        list_resp = await client.get("/api/admin/users/?skip=0&limit=10")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 2

        get_resp = await client.get(f"/api/admin/users/{created_user['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["email"] == "viewer@example.com"

        patch_resp = await client.patch(
            f"/api/admin/users/{created_user['id']}",
            json={"full_name": "Viewer", "is_active": True},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["full_name"] == "Viewer"

        delete_resp = await client.delete(f"/api/admin/users/{created_user['id']}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["is_active"] is False


async def test_viewer_gets_403_on_admin_endpoints(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "admin_forbidden.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")
        await _register(client, "viewer@example.com")

        await _login(client, "viewer@example.com")

        list_resp = await client.get("/api/admin/users/")
        assert list_resp.status_code == 403

        create_resp = await client.post(
            "/api/admin/users/",
            json={"email": "x@example.com", "password": "password123"},
        )
        assert create_resp.status_code == 403

        get_resp = await client.get("/api/admin/users/00000000-0000-0000-0000-000000000000")
        assert get_resp.status_code == 403

        patch_resp = await client.patch(
            "/api/admin/users/00000000-0000-0000-0000-000000000000",
            json={"full_name": "Nope"},
        )
        assert patch_resp.status_code == 403

        delete_resp = await client.delete("/api/admin/users/00000000-0000-0000-0000-000000000000")
        assert delete_resp.status_code == 403


async def test_cannot_delete_self(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "admin_self_delete.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        admin = await _register(client, "admin@example.com")

        response = await client.delete(f"/api/admin/users/{admin['id']}")

    assert response.status_code == 400


async def test_cannot_remove_own_superuser_flag(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "admin_self_superuser.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        admin = await _register(client, "admin@example.com")

        response = await client.patch(
            f"/api/admin/users/{admin['id']}",
            json={"is_superuser": False},
        )

    assert response.status_code == 400
