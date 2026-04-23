import time
from typing import cast

import httpx
import jwt


class GitHubAppAuth:
    def __init__(self, app_id: int, private_key: str):
        self._app_id = app_id
        self._private_key = private_key
        self._jwt_cache: tuple[str, float] | None = None
        self._token_cache: dict[int, tuple[str, float]] = {}

    def generate_jwt(self) -> str:
        now = time.time()
        if self._jwt_cache and self._jwt_cache[1] > now + 60:
            return self._jwt_cache[0]

        iat = int(now) - 60
        exp = int(now) + (10 * 60)
        payload = {"iss": str(self._app_id), "iat": iat, "exp": exp}
        token = jwt.encode(payload, self._private_key, algorithm="RS256")
        self._jwt_cache = (token, float(exp))
        return token

    async def get_installation_token(
        self, installation_id: int, http_client: httpx.AsyncClient
    ) -> str:
        now = time.time()
        cached = self._token_cache.get(installation_id)
        if cached and cached[1] > now + 300:
            return cached[0]

        jwt_token = self.generate_jwt()
        response = await http_client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        data = cast("dict[str, object]", response.json())
        token = cast("str", data["token"])
        expires_at = now + 3600
        self._token_cache[installation_id] = (token, expires_at)
        return token

    async def discover_installation_id(self, repo: str, http_client: httpx.AsyncClient) -> int:
        """Look up the installation ID for a repository using App JWT auth."""
        jwt_token = self.generate_jwt()
        response = await http_client.get(
            f"https://api.github.com/repos/{repo}/installation",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code == 404:
            raise ValueError(f"GitHub App is not installed on repository '{repo}'")
        response.raise_for_status()
        data = cast("dict[str, object]", response.json())
        return cast("int", data["id"])
