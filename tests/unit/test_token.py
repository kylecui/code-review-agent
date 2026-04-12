from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from agent_review.auth.token import create_access_token_with_secret, decode_access_token


def test_create_and_decode() -> None:
    user_id = uuid.uuid4()
    token = create_access_token_with_secret(
        user_id=user_id,
        is_superuser=True,
        secret_key="test-secret",
    )

    payload = decode_access_token(token, "test-secret")
    assert payload.sub == str(user_id)
    assert payload.is_superuser is True
    assert payload.exp is not None


def test_expired_token() -> None:
    token = create_access_token_with_secret(
        user_id=uuid.uuid4(),
        is_superuser=False,
        secret_key="test-secret",
        expires_delta=timedelta(minutes=-1),
    )

    with pytest.raises(jwt.PyJWTError):
        _ = decode_access_token(token, "test-secret")


def test_invalid_signature() -> None:
    token = create_access_token_with_secret(
        user_id=uuid.uuid4(),
        is_superuser=False,
        secret_key="test-secret",
    )
    tampered = token + "x"

    with pytest.raises(jwt.PyJWTError):
        _ = decode_access_token(tampered, "test-secret")


def test_invalid_token_format() -> None:
    with pytest.raises(jwt.PyJWTError):
        _ = decode_access_token("not-a-token", "test-secret")
