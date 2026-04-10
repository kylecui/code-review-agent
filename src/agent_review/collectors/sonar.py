import time
from typing import Any

import httpx

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.config import Settings


class SonarCollector(AbstractCollector):
    name = "sonar"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            host = self._settings.sonar_host_url
            token = self._settings.sonar_token
            if host is None or token is None or not token.get_secret_value():
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error="Sonar configuration missing",
                )

            auth = (token.get_secret_value(), "")
            project_key = context.repo

            quality_response = await self._http.get(
                f"{host}/api/qualitygates/project_status",
                params={"projectKey": project_key, "pullRequest": context.pr_number},
                auth=auth,
            )
            if quality_response.status_code >= 400:
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"Sonar quality gate error: {quality_response.status_code}",
                )

            issues_response = await self._http.get(
                f"{host}/api/issues/search",
                params={
                    "componentKeys": project_key,
                    "pullRequest": context.pr_number,
                    "types": "BUG,VULNERABILITY,CODE_SMELL",
                },
                auth=auth,
            )
            if issues_response.status_code >= 400:
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"Sonar issues error: {issues_response.status_code}",
                )

            quality_payload = quality_response.json()
            issues_payload = issues_response.json()
            issues_obj = issues_payload.get("issues", [])

            findings: list[dict[str, object]] = []
            if isinstance(issues_obj, list):
                for issue in issues_obj:
                    if not isinstance(issue, dict):
                        continue
                    findings.append(self._parse_issue(issue))

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=findings,
                duration_ms=self._duration_ms(started),
                metadata={"quality_gate": self._extract_quality_status(quality_payload)},
            )
        except Exception as exc:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
            )

    @staticmethod
    def _parse_issue(issue: dict[str, object]) -> dict[str, object]:
        line_obj = issue.get("line")
        return {
            "key": str(issue.get("key", "")),
            "rule": str(issue.get("rule", "")),
            "severity": str(issue.get("severity", "")),
            "type": str(issue.get("type", "")),
            "message": str(issue.get("message", "")),
            "component": str(issue.get("component", "")),
            "line": line_obj if isinstance(line_obj, int) else 0,
        }

    @staticmethod
    def _extract_quality_status(payload: dict[str, Any]) -> str:
        project_status = payload.get("projectStatus")
        if isinstance(project_status, dict):
            status = project_status.get("status")
            if status is not None:
                return str(status)
        return "unknown"

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
