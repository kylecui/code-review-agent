import hashlib
import hmac
import json
import uuid

import httpx
from sqlalchemy import select

from agent_review.app import create_app
from agent_review.config import Settings
from agent_review.models import Base, ReviewRun, ReviewState


def _payload(head_sha: str = "a" * 40) -> dict[str, object]:
    return {
        "action": "opened",
        "sender": {"type": "User"},
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 12345},
        "pull_request": {
            "number": 10,
            "draft": False,
            "head": {"sha": head_sha},
            "base": {"sha": "b" * 40},
        },
    }


def _headers(secret: str, body: bytes, delivery_id: str) -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": delivery_id,
    }


async def test_duplicate_delivery_id_ignored(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'idem1.db'}",
            github_webhook_secret="test-secret",
        )
    )

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        payload = _payload()
        body = json.dumps(payload).encode()
        delivery_id = str(uuid.uuid4())
        headers = _headers("test-secret", body, delivery_id)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.post("/webhooks/github", content=body, headers=headers)
            second = await client.post("/webhooks/github", content=body, headers=headers)

        assert first.status_code == 200
        assert first.json()["status"] == "queued"
        assert second.status_code == 200
        assert second.json() == {"status": "ignored", "reason": "duplicate_delivery"}


async def test_duplicate_repo_pr_sha_ignored(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'idem2.db'}",
            github_webhook_secret="test-secret",
        )
    )

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        payload = _payload(head_sha="c" * 40)
        body = json.dumps(payload).encode()

        headers1 = _headers("test-secret", body, str(uuid.uuid4()))
        headers2 = _headers("test-secret", body, str(uuid.uuid4()))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.post("/webhooks/github", content=body, headers=headers1)
            second = await client.post("/webhooks/github", content=body, headers=headers2)

        assert first.status_code == 200
        assert first.json()["status"] == "queued"
        assert second.status_code == 200
        assert second.json() == {"status": "ignored", "reason": "duplicate_run"}


async def test_new_event_creates_review_run(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'idem3.db'}",
            github_webhook_secret="test-secret",
        )
    )

    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        payload = _payload(head_sha="d" * 40)
        body = json.dumps(payload).encode()
        headers = _headers("test-secret", body, str(uuid.uuid4()))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/github", content=body, headers=headers)

        assert response.status_code == 200
        response_payload = response.json()
        assert response_payload["status"] == "queued"

        async with app.state.session_factory() as session:
            result = await session.execute(select(ReviewRun))
            runs = result.scalars().all()

        assert len(runs) == 1
        assert runs[0].repo == "owner/repo"
        assert runs[0].pr_number == 10
        assert runs[0].head_sha == "d" * 40
        assert runs[0].state == ReviewState.PENDING
