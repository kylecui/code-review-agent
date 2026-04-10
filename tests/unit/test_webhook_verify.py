import pytest
from fastapi import HTTPException

from agent_review.api.webhooks import verify_signature


def test_valid_hmac_signature_passes() -> None:
    payload = b'{"a":1}'
    secret = "webhook-secret"
    import hashlib
    import hmac

    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    verify_signature(payload, signature, secret)


def test_missing_signature_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"{}", None, "secret")
    assert exc_info.value.status_code == 401


def test_invalid_signature_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"{}", "sha256=deadbeef", "secret")
    assert exc_info.value.status_code == 401


def test_wrong_signature_format_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_signature(b"{}", "md5=deadbeef", "secret")
    assert exc_info.value.status_code == 401
