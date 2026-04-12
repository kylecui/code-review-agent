from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base

if TYPE_CHECKING:
    from pathlib import Path

VALID_YAML = """
version: 1
collectors:
  semgrep:
    failure_mode: required
    timeout_seconds: 120
    retries: 1
profiles:
  default:
    blocking_categories:
      - "security.*"
    max_inline_comments: 25
limits:
  max_inline_comments: 25
  max_summary_findings: 10
  max_diff_lines: 10000
"""


async def _init_tables(app) -> None:
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _settings(db_path: str, policy_dir: Path | None = None) -> Settings:
    if policy_dir is None:
        return Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            github_webhook_secret=SecretStr("s"),
            secret_key=SecretStr("test-secret-key"),
        )
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        github_webhook_secret=SecretStr("s"),
        secret_key=SecretStr("test-secret-key"),
        policy_dir=policy_dir,
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


async def test_list_policies_empty(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "list_empty.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.get("/api/admin/policies/")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_and_get_policy(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "create_get.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        put_response = await client.put("/api/admin/policies/default", json={"content": VALID_YAML})
        assert put_response.status_code == 200
        put_etag = put_response.headers.get("etag")
        assert put_etag is not None

        get_response = await client.get("/api/admin/policies/default")

    assert get_response.status_code == 200
    assert get_response.json()["name"] == "default"
    assert get_response.json()["content"] == VALID_YAML
    assert get_response.json()["etag"] == put_response.json()["etag"]
    assert get_response.headers.get("etag") == put_etag


async def test_update_policy_with_etag(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "update_etag.db")))

    updated_yaml = VALID_YAML + "\nexceptions:\n  emergency_bypass_labels:\n    - hotfix\n"

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        create_response = await client.put(
            "/api/admin/policies/default", json={"content": VALID_YAML}
        )
        assert create_response.status_code == 200
        etag = create_response.json()["etag"]

        update_response = await client.put(
            "/api/admin/policies/default",
            json={"content": updated_yaml},
            headers={"If-Match": f'"{etag}"'},
        )

    assert update_response.status_code == 200
    assert update_response.json()["content"] == updated_yaml
    assert update_response.json()["etag"] != etag
    assert update_response.headers.get("etag") == f'"{update_response.json()["etag"]}"'


async def test_update_policy_stale_etag(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "stale_etag.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        create_response = await client.put(
            "/api/admin/policies/default", json={"content": VALID_YAML}
        )
        assert create_response.status_code == 200

        update_response = await client.put(
            "/api/admin/policies/default",
            json={"content": VALID_YAML + "\nversion: 1\n"},
            headers={"If-Match": '"stale-etag"'},
        )

    assert update_response.status_code == 409
    detail = update_response.json()["detail"]
    assert detail["message"] == "ETag mismatch"
    assert detail["current"]["name"] == "default"
    assert detail["current"]["content"] == VALID_YAML


async def test_update_policy_no_if_match(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "no_if_match.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        create_response = await client.put(
            "/api/admin/policies/default", json={"content": VALID_YAML}
        )
        assert create_response.status_code == 200

        update_response = await client.put(
            "/api/admin/policies/default",
            json={"content": VALID_YAML + "\nexceptions:\n  emergency_bypass_labels: []\n"},
        )

    assert update_response.status_code == 428


async def test_put_invalid_yaml(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "invalid_yaml.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.put("/api/admin/policies/default", json={"content": "{{{"})

    assert response.status_code == 422


async def test_put_invalid_policy_schema(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "invalid_schema.db")))
    invalid_yaml = "version: not-a-number"

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.put("/api/admin/policies/default", json={"content": invalid_yaml})

    assert response.status_code == 422


async def test_delete_policy(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "delete_policy.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        create_response = await client.put(
            "/api/admin/policies/default", json={"content": VALID_YAML}
        )
        assert create_response.status_code == 200

        delete_response = await client.delete("/api/admin/policies/default")
        assert delete_response.status_code == 200

        get_response = await client.get("/api/admin/policies/default")

    assert get_response.status_code == 404


async def test_delete_nonexistent(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "delete_nonexistent.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.delete("/api/admin/policies/nonexistent")

    assert response.status_code == 404


async def test_seed_policies(tmp_path) -> None:
    seed_dir = tmp_path / "seed_policies"
    seed_dir.mkdir()
    (seed_dir / "default.policy.yaml").write_text(VALID_YAML, encoding="utf-8")

    app = create_app(_settings(str(tmp_path / "seed.db"), policy_dir=seed_dir))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")

        response = await client.post("/api/admin/policies/seed")

        list_response = await client.get("/api/admin/policies/")

    assert response.status_code == 200
    assert "default.policy" in response.json()["imported"]
    assert list_response.status_code == 200
    assert any(item["name"] == "default.policy" for item in list_response.json())


async def test_requires_auth(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "auth_required.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        response = await client.get("/api/admin/policies/")

    assert response.status_code == 401


async def test_requires_superuser(tmp_path) -> None:
    app = create_app(_settings(str(tmp_path / "superuser_required.db")))

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _init_tables(app)
        await _register(client, "admin@example.com")
        await _register(client, "viewer@example.com")
        await _login(client, "viewer@example.com")

        response = await client.get("/api/admin/policies/")

    assert response.status_code == 403
