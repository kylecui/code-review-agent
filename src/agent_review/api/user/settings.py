from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from agent_review.auth.dependencies import get_current_user
from agent_review.crypto import decrypt_value, encrypt_value, mask_secret
from agent_review.models import User
from agent_review.models.user_settings import UserSettings

router = APIRouter(tags=["user-settings"])
CurrentUser = Annotated[User, Depends(get_current_user)]

USER_CONFIGURABLE_KEYS: set[str] = {
    "llm_openai_api_key",
    "llm_gemini_api_key",
    "llm_github_api_key",
    "llm_anthropic_api_key",
    "llm_classify_model",
    "llm_synthesize_model",
    "llm_fallback_model",
    "llm_temperature",
}

SECRET_KEYS: set[str] = {
    "llm_openai_api_key",
    "llm_gemini_api_key",
    "llm_github_api_key",
    "llm_anthropic_api_key",
}


def _serialize_value(value: Any) -> str:
    return json.dumps(value)


def _deserialize_value(value: str) -> Any:
    return json.loads(value)


def _validate_key(key: str) -> None:
    if key not in USER_CONFIGURABLE_KEYS:
        raise HTTPException(status_code=422, detail=f"Setting '{key}' is not editable")


async def _resolve_settings_payload(
    request: Request, current_user: User
) -> dict[str, dict[str, Any]]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(
            select(UserSettings).where(
                UserSettings.user_id == current_user.id,
                UserSettings.key.in_(USER_CONFIGURABLE_KEYS),
            )
        )
        overrides = {record.key: record for record in result.scalars().all()}

    payload: dict[str, dict[str, Any]] = {}
    for key in sorted(USER_CONFIGURABLE_KEYS):
        override = overrides.get(key)
        if override is None:
            payload[key] = {"value": None, "source": "default"}
            continue

        if key in SECRET_KEYS:
            decrypted = decrypt_value(_deserialize_value(override.value), secret_key)
            payload[key] = {"value": mask_secret(decrypted), "source": "db"}
            continue

        payload[key] = {"value": _deserialize_value(override.value), "source": "db"}

    return payload


@router.get("/")
async def get_settings(request: Request, current_user: CurrentUser) -> dict[str, Any]:
    return {"settings": await _resolve_settings_payload(request, current_user)}


@router.put("/")
async def update_settings(
    body: dict[str, Any], request: Request, current_user: CurrentUser
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    for key in body:
        _validate_key(key)

    async with session_factory() as db:
        for key, value in body.items():
            result = await db.execute(
                select(UserSettings).where(
                    UserSettings.user_id == current_user.id,
                    UserSettings.key == key,
                )
            )
            existing = result.scalar_one_or_none()

            if key in SECRET_KEYS:
                value_str = value if isinstance(value, str) else str(value)
                if "****" in value_str:
                    continue

                if value_str == "":
                    if existing is not None:
                        await db.delete(existing)
                    continue

                encrypted_value = _serialize_value(encrypt_value(value_str, secret_key))
                if existing is None:
                    db.add(
                        UserSettings(
                            id=uuid.uuid4(),
                            user_id=current_user.id,
                            key=key,
                            value=encrypted_value,
                        )
                    )
                else:
                    existing.value = encrypted_value
                continue

            serialized_value = _serialize_value(value)
            if existing is None:
                db.add(
                    UserSettings(
                        id=uuid.uuid4(),
                        user_id=current_user.id,
                        key=key,
                        value=serialized_value,
                    )
                )
            else:
                existing.value = serialized_value

        await db.commit()

    return {"settings": await _resolve_settings_payload(request, current_user)}


@router.delete("/{key}")
async def delete_setting(key: str, request: Request, current_user: CurrentUser) -> dict[str, str]:
    _validate_key(key)

    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        result = await db.execute(
            select(UserSettings).where(
                UserSettings.user_id == current_user.id,
                UserSettings.key == key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=404, detail="Override not found")

        await db.delete(existing)
        await db.commit()

    return {"status": "ok"}
