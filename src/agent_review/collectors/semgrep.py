import time

import httpx

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.config import Settings


class SemgrepCollector(AbstractCollector):
    name = "semgrep"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            mode = self._settings.semgrep_mode
            if mode == "disabled":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode},
                )

            if mode == "cli":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode, "reason": "cli_stub"},
                )

            token = self._settings.semgrep_app_token
            if token is None or not token.get_secret_value():
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error="Semgrep app token missing",
                    metadata={"mode": mode},
                )

            deployment = context.repo
            response = await self._http.get(
                f"https://semgrep.dev/api/v1/deployments/{deployment}/findings",
                params={"repo": context.repo, "ref": context.head_sha},
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
            )

            if response.status_code >= 400:
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"Semgrep API error: {response.status_code}",
                    metadata={"mode": mode},
                )

            payload = response.json()
            findings_payload = payload.get("findings", [])
            raw_findings: list[dict[str, object]] = []
            if isinstance(findings_payload, list):
                for finding in findings_payload:
                    if not isinstance(finding, dict):
                        continue
                    path_obj = finding.get("path")
                    extra_obj = finding.get("extra")
                    extra = extra_obj if isinstance(extra_obj, dict) else {}
                    start_obj = finding.get("start")
                    start = start_obj if isinstance(start_obj, dict) else {}
                    raw_findings.append(
                        {
                            "rule_id": str(finding.get("check_id", "")),
                            "path": str(path_obj) if path_obj is not None else "",
                            "line": int(start.get("line", 0))
                            if isinstance(start.get("line"), int)
                            else 0,
                            "severity": str(extra.get("severity", "")),
                            "message": str(extra.get("message", "")),
                        }
                    )

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=raw_findings,
                duration_ms=self._duration_ms(started),
                metadata={"mode": mode},
            )
        except Exception as exc:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
                metadata={"mode": self._settings.semgrep_mode},
            )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
