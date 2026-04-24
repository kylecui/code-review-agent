from urllib.parse import urlencode

import httpx


def build_github_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "read:user user:email",
        }
    )
    return f"https://github.com/login/oauth/authorize?{params}"


async def exchange_code_for_token(client_id: str, client_secret: str, code: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        raw_token = data.get("access_token", "")
        if not raw_token:
            raise ValueError("Missing GitHub access_token")
        return str(raw_token)


async def fetch_github_user(access_token: str) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid GitHub user payload")
        return data
