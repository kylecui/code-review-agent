from __future__ import annotations

import json
import uuid

from pydantic import SecretStr

from agent_review.config import Settings
from agent_review.crypto import encrypt_value
from agent_review.models.app_config import AppConfig
from agent_review.models.user import User
from agent_review.models.user_settings import UserSettings
from agent_review.pipeline.analysis import _resolve_api_keys

_TEST_SECRET = "test-secret"


def _settings() -> Settings:
    return Settings(
        secret_key=SecretStr(_TEST_SECRET),
        llm_openai_api_key=SecretStr("env-openai"),
        llm_gemini_api_key=SecretStr("env-gemini"),
        llm_github_api_key=SecretStr("env-github"),
        llm_anthropic_api_key=SecretStr("env-anthropic"),
    )


def _enc(value: str) -> str:
    return json.dumps(encrypt_value(value, _TEST_SECRET))


def _make_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )


async def test_resolve_api_keys_user_override_takes_priority(async_engine, db_session) -> None:
    assert async_engine is not None
    user_id = uuid.uuid4()
    db_session.add(_make_user(user_id))
    db_session.add(
        AppConfig(
            id=uuid.uuid4(),
            key="llm_openai_api_key",
            value=_enc("global-openai"),
        )
    )
    db_session.add(
        UserSettings(
            id=uuid.uuid4(),
            user_id=user_id,
            key="llm_openai_api_key",
            value=_enc("user-openai"),
        )
    )
    await db_session.commit()

    resolved = await _resolve_api_keys(db_session, _settings(), user_id=user_id)

    assert resolved["llm_openai_api_key"] == "user-openai"


async def test_resolve_api_keys_falls_back_to_global_when_no_user_override(
    async_engine, db_session
) -> None:
    assert async_engine is not None
    user_id = uuid.uuid4()
    db_session.add(_make_user(user_id))
    db_session.add(
        AppConfig(
            id=uuid.uuid4(),
            key="llm_gemini_api_key",
            value=_enc("global-gemini"),
        )
    )
    await db_session.commit()

    resolved = await _resolve_api_keys(db_session, _settings(), user_id=user_id)

    assert resolved["llm_gemini_api_key"] == "global-gemini"


async def test_resolve_api_keys_falls_back_to_env_when_no_global_override(
    async_engine, db_session
) -> None:
    assert async_engine is not None
    user_id = uuid.uuid4()
    db_session.add(_make_user(user_id))
    await db_session.commit()

    resolved = await _resolve_api_keys(db_session, _settings(), user_id=user_id)

    assert resolved["llm_github_api_key"] == "env-github"


async def test_resolve_api_keys_user_none_skips_user_layer(async_engine, db_session) -> None:
    assert async_engine is not None
    user_id = uuid.uuid4()
    db_session.add(_make_user(user_id))
    db_session.add(
        UserSettings(
            id=uuid.uuid4(),
            user_id=user_id,
            key="llm_anthropic_api_key",
            value=_enc("user-anthropic"),
        )
    )
    db_session.add(
        AppConfig(
            id=uuid.uuid4(),
            key="llm_anthropic_api_key",
            value=_enc("global-anthropic"),
        )
    )
    await db_session.commit()

    resolved = await _resolve_api_keys(db_session, _settings(), user_id=None)

    assert resolved["llm_anthropic_api_key"] == "global-anthropic"


async def test_resolve_api_keys_mixed_sources_resolve_independently(
    async_engine, db_session
) -> None:
    assert async_engine is not None
    user_id = uuid.uuid4()
    db_session.add(_make_user(user_id))
    db_session.add_all(
        [
            UserSettings(
                id=uuid.uuid4(),
                user_id=user_id,
                key="llm_openai_api_key",
                value=_enc("user-openai"),
            ),
            UserSettings(
                id=uuid.uuid4(),
                user_id=user_id,
                key="llm_anthropic_api_key",
                value=_enc("user-anthropic"),
            ),
            AppConfig(
                id=uuid.uuid4(),
                key="llm_openai_api_key",
                value=_enc("global-openai"),
            ),
            AppConfig(
                id=uuid.uuid4(),
                key="llm_gemini_api_key",
                value=_enc("global-gemini"),
            ),
        ]
    )
    await db_session.commit()

    resolved = await _resolve_api_keys(db_session, _settings(), user_id=user_id)

    assert resolved["llm_openai_api_key"] == "user-openai"
    assert resolved["llm_gemini_api_key"] == "global-gemini"
    assert resolved["llm_github_api_key"] == "env-github"
    assert resolved["llm_anthropic_api_key"] == "user-anthropic"
