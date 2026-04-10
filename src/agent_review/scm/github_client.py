import asyncio
import random
from typing import Any, cast

import httpx

from agent_review.scm.github_auth import GitHubAppAuth


class GitHubClient:
    BASE_URL: str = "https://api.github.com"

    def __init__(self, http_client: httpx.AsyncClient, auth: GitHubAppAuth, installation_id: int):
        self._http: httpx.AsyncClient = http_client
        self._auth: GitHubAppAuth = auth
        self._installation_id: int = installation_id

    async def _get_token(self) -> str:
        return await self._auth.get_installation_token(self._installation_id, self._http)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._get_token()
        extra_headers_obj = kwargs.pop("headers", None)
        extra_headers: dict[str, str]
        if isinstance(extra_headers_obj, dict):
            extra_headers = {str(key): str(value) for key, value in extra_headers_obj.items()}
        else:
            extra_headers = {}

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            **extra_headers,
        }

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            response = await self._http.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=headers,
                **kwargs,
            )
            is_rate_limited = response.status_code == 429 or (
                response.status_code == 403 and "rate limit" in response.text.lower()
            )
            if is_rate_limited:
                if attempt == max_retries:
                    _ = response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    delay = float(retry_after)
                else:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                await asyncio.sleep(min(delay, 60.0))
                continue

            _ = response.raise_for_status()
            return response

        raise RuntimeError("Unreachable")

    async def create_check_run(
        self,
        repo: str,
        head_sha: str,
        name: str,
        external_id: str,
        status: str = "in_progress",
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/repos/{repo}/check-runs",
            json={
                "name": name,
                "head_sha": head_sha,
                "external_id": external_id,
                "status": status,
            },
        )
        return cast("dict[str, Any]", response.json())

    async def update_check_run(
        self,
        repo: str,
        check_run_id: int,
        *,
        status: str | None = None,
        conclusion: str | None = None,
        output: dict[str, Any] | None = None,
        annotations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if status:
            body["status"] = status
        if conclusion:
            body["conclusion"] = conclusion
        if output:
            body["output"] = output

        if annotations:
            for index in range(0, len(annotations), 50):
                batch = annotations[index : index + 50]
                batch_output = {**(output or {}), "annotations": batch}
                body_with_annotations = {**body, "output": batch_output}
                await self._request(
                    "PATCH",
                    f"/repos/{repo}/check-runs/{check_run_id}",
                    json=body_with_annotations,
                )
            return {}

        response = await self._request(
            "PATCH",
            f"/repos/{repo}/check-runs/{check_run_id}",
            json=body,
        )
        return cast("dict[str, Any]", response.json())

    async def create_review(
        self,
        repo: str,
        pr_number: int,
        commit_id: str,
        event: str,
        body: str,
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "event": event,
            "body": body,
        }
        if comments:
            payload["comments"] = comments
        response = await self._request(
            "POST",
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        return cast("dict[str, Any]", response.json())

    async def dismiss_review(
        self, repo: str, pr_number: int, review_id: int, message: str
    ) -> dict[str, Any]:
        response = await self._request(
            "PUT",
            f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
            json={"message": message},
        )
        return cast("dict[str, Any]", response.json())

    async def list_reviews(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        response = await self._request("GET", f"/repos/{repo}/pulls/{pr_number}/reviews")
        return cast("list[dict[str, Any]]", response.json())

    async def list_issue_comments(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        response = await self._request("GET", f"/repos/{repo}/issues/{pr_number}/comments")
        return cast("list[dict[str, Any]]", response.json())

    async def create_issue_comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        return cast("dict[str, Any]", response.json())

    async def patch_issue_comment(self, repo: str, comment_id: int, body: str) -> dict[str, Any]:
        response = await self._request(
            "PATCH",
            f"/repos/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        return cast("dict[str, Any]", response.json())

    async def upsert_comment(
        self, repo: str, pr_number: int, sentinel: str, body: str
    ) -> dict[str, Any]:
        comments = await self.list_issue_comments(repo, pr_number)
        for comment in comments:
            if sentinel in str(comment.get("body", "")):
                comment_id = int(comment["id"])
                return await self.patch_issue_comment(repo, comment_id, body)
        return await self.create_issue_comment(repo, pr_number, body)

    async def get_pr(self, repo: str, pr_number: int) -> dict[str, Any]:
        response = await self._request("GET", f"/repos/{repo}/pulls/{pr_number}")
        return cast("dict[str, Any]", response.json())

    async def get_pr_files(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        response = await self._request("GET", f"/repos/{repo}/pulls/{pr_number}/files")
        return cast("list[dict[str, Any]]", response.json())
