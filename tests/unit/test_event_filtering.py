import hashlib
import hmac
import json
import uuid

import httpx

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base


def _build_payload(
    *,
    action: str = "opened",
    sender_type: str = "User",
    draft: bool = False,
    head_sha: str = "a" * 40,
) -> dict[str, object]:
    return {
        "action": action,
        "sender": {"type": sender_type},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 12345},
        "pull_request": {
            "number": 7,
            "draft": draft,
            "head": {"sha": head_sha},
            "base": {"sha": "b" * 40},
        },
    }


def _headers(secret: str, payload_bytes: bytes, *, event: str = "pull_request") -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": str(uuid.uuid4()),
    }


async def test_non_pull_request_event_ignored(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event1.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload()

    body = json.dumps(payload).encode()
    headers = _headers(secret, body, event="push")

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "not_pull_request"}


async def test_invalid_action_ignored(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event2.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload(action="closed")

    body = json.dumps(payload).encode()
    headers = _headers(secret, body)

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "action_closed_not_handled"}


async def test_bot_sender_ignored(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event3.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload(sender_type="Bot")

    body = json.dumps(payload).encode()
    headers = _headers(secret, body)

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "bot_sender"}


async def test_draft_pr_ignored(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event4.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload(draft=True, action="opened")

    body = json.dumps(payload).encode()
    headers = _headers(secret, body)

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "draft_pr"}


async def test_non_draft_valid_action_proceeds(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event5.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload(draft=False, action="opened")

    body = json.dumps(payload).encode()
    headers = _headers(secret, body)

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    payload_json = response.json()
    assert payload_json["status"] == "queued"
    assert "run_id" in payload_json


async def test_ready_for_review_on_draft_proceeds(tmp_path) -> None:
    secret = "test-secret"
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'event6.db'}",
            github_webhook_secret=secret,
        )
    )
    payload = _build_payload(draft=True, action="ready_for_review")

    body = json.dumps(payload).encode()
    headers = _headers(secret, body)

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    payload_json = response.json()
    assert payload_json["status"] == "queued"
    assert "run_id" in payload_json
