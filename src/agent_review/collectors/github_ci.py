import time
from typing import Any

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult


class GitHubCICollector(AbstractCollector):
    name = "github_ci"

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            if context.github_client is None or context.run_kind == "baseline":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error="CI collector requires a pull request with GitHub access",
                )

            checks_payload = await context.github_client._request(
                "GET",
                f"/repos/{context.repo}/commits/{context.head_sha}/check-runs",
            )
            checks_json = checks_payload.json()
            check_runs_obj = (
                checks_json.get("check_runs", []) if isinstance(checks_json, dict) else []
            )

            findings: list[dict[str, object]] = []
            workflow_run_ids: set[int] = set()

            if isinstance(check_runs_obj, list):
                for check_run in check_runs_obj:
                    if not isinstance(check_run, dict):
                        continue
                    check_run_id = check_run.get("id")
                    if isinstance(check_run.get("check_suite"), dict):
                        suite = check_run["check_suite"]
                        workflow_id = suite.get("id")
                        if isinstance(workflow_id, int):
                            workflow_run_ids.add(workflow_id)

                    if isinstance(check_run_id, int):
                        annotations_response = await context.github_client._request(
                            "GET",
                            f"/repos/{context.repo}/check-runs/{check_run_id}/annotations",
                        )
                        annotations = annotations_response.json()
                        if isinstance(annotations, list):
                            for annotation in annotations:
                                if isinstance(annotation, dict):
                                    findings.append(self._parse_annotation(check_run, annotation))

            artifacts_count = 0
            for run_id in workflow_run_ids:
                artifacts_response = await context.github_client._request(
                    "GET",
                    f"/repos/{context.repo}/actions/runs/{run_id}/artifacts",
                )
                artifacts_json = artifacts_response.json()
                artifacts_obj = (
                    artifacts_json.get("artifacts", []) if isinstance(artifacts_json, dict) else []
                )
                if isinstance(artifacts_obj, list):
                    artifacts_count += len(artifacts_obj)

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=findings,
                duration_ms=self._duration_ms(started),
                metadata={"artifacts_count": artifacts_count},
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
    def _parse_annotation(
        check_run: dict[str, Any], annotation: dict[str, Any]
    ) -> dict[str, object]:
        return {
            "check_name": str(check_run.get("name", "")),
            "status": str(check_run.get("conclusion", "")),
            "path": str(annotation.get("path", "")),
            "start_line": int(annotation.get("start_line", 0))
            if isinstance(annotation.get("start_line"), int)
            else 0,
            "end_line": int(annotation.get("end_line", 0))
            if isinstance(annotation.get("end_line"), int)
            else 0,
            "annotation_level": str(annotation.get("annotation_level", "")),
            "message": str(annotation.get("message", "")),
            "title": str(annotation.get("title", "")),
        }

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
