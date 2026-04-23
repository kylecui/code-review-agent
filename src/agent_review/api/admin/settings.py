from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import SecretStr
from sqlalchemy import select

from agent_review.auth.dependencies import get_current_superuser
from agent_review.crypto import decrypt_value, encrypt_value, mask_secret
from agent_review.models import User
from agent_review.models.app_config import AppConfig

router = APIRouter(tags=["admin-settings"])
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]

OPERATIONAL_KEYS: set[str] = {
    "llm_classify_model",
    "llm_synthesize_model",
    "llm_fallback_model",
    "llm_openai_api_key",
    "llm_gemini_api_key",
    "llm_github_api_key",
    "llm_anthropic_api_key",
    "llm_max_tokens",
    "llm_temperature",
    "llm_cost_budget_per_run_cents",
    "semgrep_mode",
    "semgrep_severity_filter",
    "max_inline_comments",
    "max_diff_lines",
    "log_level",
}

SECRET_KEYS: set[str] = {
    "llm_openai_api_key",
    "llm_gemini_api_key",
    "llm_github_api_key",
    "llm_anthropic_api_key",
}


def _normalize_setting_value(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, Path):
        return str(value)
    return value


def _serialize_value(value: Any) -> str:
    return json.dumps(value)


def _deserialize_value(value: str) -> Any:
    return json.loads(value)


def _validate_key(key: str) -> None:
    if key not in OPERATIONAL_KEYS:
        raise HTTPException(status_code=422, detail=f"Setting '{key}' is not editable")


async def _resolve_settings_payload(request: Request) -> dict[str, dict[str, Any]]:
    session_factory = request.app.state.session_factory
    settings = request.app.state.settings
    secret_key = settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(select(AppConfig).where(AppConfig.key.in_(OPERATIONAL_KEYS)))
        overrides = {record.key: record for record in result.scalars().all()}

    payload: dict[str, dict[str, Any]] = {}
    for key in sorted(OPERATIONAL_KEYS):
        override = overrides.get(key)
        is_secret = key in SECRET_KEYS
        if override is None:
            env_value = _normalize_setting_value(getattr(settings, key))
            if is_secret:
                is_set = bool(env_value)
                payload[key] = {
                    "value": mask_secret(str(env_value)) if is_set else "",
                    "source": "env",
                    "is_set": is_set,
                }
                continue
            payload[key] = {
                "value": env_value,
                "source": "env",
                "is_set": True,
            }
        else:
            if is_secret:
                decrypted = decrypt_value(_deserialize_value(override.value), secret_key)
                payload[key] = {
                    "value": mask_secret(decrypted),
                    "source": "db",
                    "is_set": True,
                }
                continue
            payload[key] = {
                "value": _deserialize_value(override.value),
                "source": "db",
                "is_set": True,
            }
    return payload


async def _resolve_secret_value(key: str, request: Request) -> str:
    """Resolve secret: DB (decrypted) > env."""
    session_factory = request.app.state.session_factory
    settings = request.app.state.settings
    secret = settings.secret_key.get_secret_value()

    async with session_factory() as db:
        result = await db.execute(select(AppConfig).where(AppConfig.key == key))
        record = result.scalar_one_or_none()

    if record is not None:
        decrypted = decrypt_value(_deserialize_value(record.value), secret)
        if decrypted:
            return decrypted

    env_val = getattr(settings, key, None)
    if isinstance(env_val, SecretStr):
        return env_val.get_secret_value()
    return ""


@router.get("/")
async def get_settings(request: Request, current_user: CurrentSuperuser) -> dict[str, Any]:
    _ = current_user
    return {"settings": await _resolve_settings_payload(request)}


@router.put("/")
async def update_settings(
    body: dict[str, Any], request: Request, current_user: CurrentSuperuser
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    secret_key = request.app.state.settings.secret_key.get_secret_value()

    for key in body:
        _validate_key(key)

    async with session_factory() as db:
        for key, value in body.items():
            if key in SECRET_KEYS:
                value_str = value if isinstance(value, str) else str(value)
                if "****" in value_str:
                    continue

                result = await db.execute(select(AppConfig).where(AppConfig.key == key))
                existing = result.scalar_one_or_none()
                if value_str == "":
                    if existing is not None:
                        await db.delete(existing)
                    continue

                encrypted_value = _serialize_value(encrypt_value(value_str, secret_key))
                if existing is None:
                    db.add(
                        AppConfig(
                            id=uuid.uuid4(),
                            key=key,
                            value=encrypted_value,
                            updated_by=current_user.id,
                        )
                    )
                else:
                    existing.value = encrypted_value
                    existing.updated_by = current_user.id
                continue

            result = await db.execute(select(AppConfig).where(AppConfig.key == key))
            existing = result.scalar_one_or_none()
            if existing is None:
                db.add(
                    AppConfig(
                        id=uuid.uuid4(),
                        key=key,
                        value=_serialize_value(value),
                        updated_by=current_user.id,
                    )
                )
            else:
                existing.value = _serialize_value(value)
                existing.updated_by = current_user.id
        await db.commit()

    return {"settings": await _resolve_settings_payload(request)}


@router.get("/models")
async def get_available_models(request: Request, current_user: CurrentSuperuser) -> dict[str, Any]:
    _ = current_user

    providers: dict[str, dict[str, Any]] = {
        "openai": {"available": False, "models": []},
        "gemini": {"available": False, "models": []},
        "github": {"available": False, "models": []},
        "anthropic": {"available": False, "models": []},
    }

    openai_key = await _resolve_secret_value("llm_openai_api_key", request)
    gemini_key = await _resolve_secret_value("llm_gemini_api_key", request)
    github_key = await _resolve_secret_value("llm_github_api_key", request)
    anthropic_key = await _resolve_secret_value("llm_anthropic_api_key", request)

    async with httpx.AsyncClient(timeout=10.0) as client:
        if openai_key:
            try:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                response.raise_for_status()
                data = response.json().get("data", [])
                models = [
                    model["id"] for model in data if isinstance(model, dict) and "id" in model
                ]
                providers["openai"] = {"available": True, "models": models}
            except Exception as exc:
                providers["openai"] = {"available": False, "error": str(exc)}

        if gemini_key:
            try:
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": gemini_key},
                )
                response.raise_for_status()
                data = response.json().get("models", [])
                models = []
                for model in data:
                    if isinstance(model, dict) and "name" in model:
                        name = str(model["name"])
                        models.append(name.removeprefix("models/"))
                providers["gemini"] = {"available": True, "models": models}
            except Exception as exc:
                providers["gemini"] = {"available": False, "error": str(exc)}

        if github_key:
            try:
                response = await client.get(
                    "https://models.inference.ai.azure.com/models",
                    headers={"Authorization": f"Bearer {github_key}"},
                )
                response.raise_for_status()
                data = response.json()
                models = [
                    model["id"] for model in data if isinstance(model, dict) and "id" in model
                ]
                providers["github"] = {"available": True, "models": models}
            except Exception as exc:
                providers["github"] = {"available": False, "error": str(exc)}

        if anthropic_key:
            try:
                response = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                response.raise_for_status()
                data = response.json().get("data", [])
                models = [
                    model["id"] for model in data if isinstance(model, dict) and "id" in model
                ]
                providers["anthropic"] = {"available": True, "models": models}
            except Exception as exc:
                providers["anthropic"] = {"available": False, "error": str(exc)}

    return {"providers": providers}


@router.delete("/{key}")
async def delete_setting(
    key: str, request: Request, current_user: CurrentSuperuser
) -> dict[str, str]:
    _ = current_user
    _validate_key(key)

    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        result = await db.execute(select(AppConfig).where(AppConfig.key == key))
        existing = result.scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=404, detail="Override not found")
        await db.delete(existing)
        await db.commit()

    return {"status": "ok"}
