import time
from typing import Any

import httpx

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.observability import get_logger

logger = get_logger(__name__)


class SecretsCollector(AbstractCollector):
    name = "secrets"

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        if context.github_client is None:
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"reason": "no_github_client"},
            )
        try:
            response = await context.github_client._request(
                "GET",
                f"/repos/{context.repo}/secret-scanning/alerts",
                params={"state": "open"},
            )
            payload = response.json()
            if not isinstance(payload, list):
                return CollectorResult(
                    collector_name=self.name,
                    status="success",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                )

            findings: list[dict[str, object]] = []
            for alert in payload:
                if not isinstance(alert, dict):
                    continue
                if context.run_kind == "baseline":
                    if not str(alert.get("resolved_at", "")):
                        findings.append(self._parse_alert(alert))
                elif self._is_relevant(alert, context.head_sha, context.base_sha or ""):
                    findings.append(self._parse_alert(alert))

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=findings,
                duration_ms=self._duration_ms(started),
            )
        except Exception as exc:
            # 404 = secret scanning not enabled for this repo, not a failure
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
                logger.info(
                    "secrets_not_enabled",
                    repo=context.repo,
                )
                return CollectorResult(
                    collector_name=self.name,
                    status="success",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"reason": "secret_scanning_not_enabled"},
                )
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
            )

    @staticmethod
    def _is_relevant(alert: dict[str, Any], head_sha: str, base_sha: str) -> bool:
        if str(alert.get("resolved_at", "")):
            return False

        commit_sha = alert.get("commit_sha")
        if isinstance(commit_sha, str) and commit_sha:
            return commit_sha in {head_sha, base_sha}

        locations = alert.get("locations")
        if isinstance(locations, list):
            for location in locations:
                if isinstance(location, dict):
                    details = location.get("details")
                    if isinstance(details, dict) and details.get("commit_sha") in {
                        head_sha,
                        base_sha,
                    }:
                        return True
        return False

    @staticmethod
    def _parse_alert(alert: dict[str, Any]) -> dict[str, object]:
        secret_type_display_name = alert.get("secret_type_display_name")
        return {
            "number": int(alert.get("number", 0)) if isinstance(alert.get("number"), int) else 0,
            "state": str(alert.get("state", "")),
            "secret_type": str(secret_type_display_name)
            if secret_type_display_name is not None
            else "",
            "html_url": str(alert.get("html_url", "")),
            "created_at": str(alert.get("created_at", "")),
        }

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
