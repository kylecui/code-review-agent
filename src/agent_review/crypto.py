from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt_value(plaintext: str, secret_key: str) -> str:
    fernet = Fernet(_derive_fernet_key(secret_key))
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(token: str, secret_key: str) -> str:
    fernet = Fernet(_derive_fernet_key(secret_key))
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]
