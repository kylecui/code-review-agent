import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agent_review.scm.github_auth import GitHubAppAuth


@pytest.fixture
def rsa_private_key_pem() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


def test_generate_jwt_claims(rsa_private_key_pem: str) -> None:
    auth = GitHubAppAuth(app_id=1234, private_key=rsa_private_key_pem)

    token = auth.generate_jwt()
    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["iss"] == "1234"
    assert claims["exp"] > claims["iat"]
    assert 500 <= claims["exp"] - claims["iat"] <= 700


def test_generate_jwt_caching(rsa_private_key_pem: str) -> None:
    auth = GitHubAppAuth(app_id=1234, private_key=rsa_private_key_pem)

    first = auth.generate_jwt()
    second = auth.generate_jwt()

    assert first == second


@pytest.mark.asyncio
@respx.mock
async def test_get_installation_token_exchange(rsa_private_key_pem: str) -> None:
    auth = GitHubAppAuth(app_id=1234, private_key=rsa_private_key_pem)
    route = respx.post("https://api.github.com/app/installations/99/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "inst_token"})
    )

    async with httpx.AsyncClient() as client:
        token = await auth.get_installation_token(99, client)

    assert token == "inst_token"
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_get_installation_token_caching(rsa_private_key_pem: str) -> None:
    auth = GitHubAppAuth(app_id=1234, private_key=rsa_private_key_pem)
    route = respx.post("https://api.github.com/app/installations/99/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "cached_inst_token"})
    )

    async with httpx.AsyncClient() as client:
        first = await auth.get_installation_token(99, client)
        second = await auth.get_installation_token(99, client)

    assert first == "cached_inst_token"
    assert second == "cached_inst_token"
    assert route.call_count == 1
