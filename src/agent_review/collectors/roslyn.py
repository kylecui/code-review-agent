from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.observability import get_logger

if TYPE_CHECKING:
    import httpx

    from agent_review.config import Settings

logger = get_logger(__name__)


class RoslynCollector(AbstractCollector):
    name = "roslyn"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            mode = self._settings.roslyn_mode
            if mode == "disabled":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode},
                )

            return await self._collect_cli(context, started)
        except Exception as exc:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
                metadata={"mode": self._settings.roslyn_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        if context.local_path is None:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="Local path is required for roslyn collector",
                metadata={"mode": "cli"},
            )

        scan_dir = Path(context.local_path)
        if not scan_dir.is_dir():
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=f"Local path does not exist: {context.local_path}",
                metadata={"mode": "cli"},
            )

        has_cs = any(
            candidate.is_file() and candidate.suffix.lower() == ".cs"
            for candidate in scan_dir.rglob("*")
        )
        if not has_cs:
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "reason": "no_csharp_files"},
            )

        project = self._find_project_or_solution(scan_dir)
        if project is None:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="No .csproj or .sln file found in scan directory",
                metadata={"mode": "cli"},
            )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_report:
            report_path = Path(temp_report.name)

        try:
            cmd = [
                "dotnet",
                "format",
                "analyzers",
                str(project),
                "--diagnostics",
                "--severity",
                self._settings.roslyn_severity,
                "--report",
                str(report_path),
                "--verify-no-changes",
            ]

            logger.info(
                "roslyn_cli_start",
                repo=context.repo,
                head_sha=context.head_sha,
                project=str(project),
            )
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            _, stderr_bytes = await proc.communicate()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode not in (0, 2):
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"dotnet format exited with code {proc.returncode}: {stderr_text[:500]}",
                    metadata={"mode": "cli"},
                )

            report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
            raw_findings = self._parse_report(report_text)

            scan_dir_prefix = str(scan_dir) + "/"
            for finding in raw_findings:
                path = str(finding.get("path", ""))
                if path.startswith(scan_dir_prefix):
                    finding["path"] = path[len(scan_dir_prefix) :]

            logger.info(
                "roslyn_cli_done",
                finding_count=len(raw_findings),
                duration_ms=self._duration_ms(started),
            )
            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=raw_findings,
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "project": str(project)},
            )
        finally:
            report_path.unlink(missing_ok=True)

    @staticmethod
    def _find_project_or_solution(scan_dir: Path) -> Path | None:
        projects = sorted(path for path in scan_dir.rglob("*.csproj") if path.is_file())
        if projects:
            return projects[0]
        solutions = sorted(path for path in scan_dir.rglob("*.sln") if path.is_file())
        if solutions:
            return solutions[0]
        return None

    @staticmethod
    def _is_security_analyzer(rule_id: str) -> bool:
        upper = rule_id.upper()
        return upper.startswith("CA21") or upper.startswith("CA30") or "SECURITY" in upper

    @classmethod
    def _map_severity(cls, severity: str, rule_id: str) -> str:
        normalized = severity.upper()
        if normalized == "ERROR":
            return "HIGH"
        if normalized == "WARNING":
            if cls._is_security_analyzer(rule_id):
                return "HIGH"
            return "MEDIUM"
        if normalized in {"INFO", "SUGGESTION", "HIDDEN"}:
            return "LOW"
        return "LOW"

    @classmethod
    def _parse_report(cls, report_text: str) -> list[dict[str, object]]:
        if not report_text.strip():
            return []
        try:
            payload = json.loads(report_text)
        except json.JSONDecodeError:
            return []

        diagnostics = payload if isinstance(payload, list) else payload.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            return []

        findings: list[dict[str, object]] = []
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            location = diagnostic.get("location", {})
            if not isinstance(location, dict):
                location = {}
            rule_id = str(diagnostic.get("id", ""))
            severity_raw = str(diagnostic.get("severity", ""))
            line_raw = location.get("line", 0)
            findings.append(
                {
                    "rule_id": rule_id,
                    "severity": cls._map_severity(severity_raw, rule_id),
                    "message": str(diagnostic.get("message", "")),
                    "path": str(location.get("path", "")),
                    "line": line_raw if isinstance(line_raw, int) else 0,
                }
            )
        return findings

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
