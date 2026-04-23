from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.observability import get_logger

if TYPE_CHECKING:
    import httpx

    from agent_review.config import Settings

logger = get_logger(__name__)


class EslintSecurityCollector(AbstractCollector):
    name = "eslint_security"

    _JS_TS_EXTENSIONS: ClassVar[set[str]] = {
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".mts",
        ".cts",
    }

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            mode = self._settings.eslint_security_mode
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
                metadata={"mode": self._settings.eslint_security_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        if context.local_path is None:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="Local path is required for eslint security collector",
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

        targets = self._build_targets(context, scan_dir)
        if not targets:
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "reason": "no_js_ts_files"},
            )

        cmd = [
            "npx",
            "eslint",
            "--no-eslintrc",
            "--config",
            self._settings.eslint_security_config_path,
            "--format",
            "json",
            *[str(target) for target in targets],
        ]
        logger.info(
            "eslint_security_cli_start",
            repo=context.repo,
            head_sha=context.head_sha,
            target_count=len(targets),
            baseline=context.run_kind == "baseline",
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(scan_dir),
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        if proc.returncode not in (0, 1):
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=f"eslint exited with code {proc.returncode}: {stderr_text[:500]}",
                metadata={"mode": "cli"},
            )

        raw_findings = self._parse_cli_output(stdout_text)
        scan_dir_prefix = str(scan_dir) + "/"
        for finding in raw_findings:
            path = str(finding.get("path", ""))
            if path.startswith(scan_dir_prefix):
                finding["path"] = path[len(scan_dir_prefix) :]

        logger.info(
            "eslint_security_cli_done",
            finding_count=len(raw_findings),
            duration_ms=self._duration_ms(started),
        )
        return CollectorResult(
            collector_name=self.name,
            status="success",
            raw_findings=raw_findings,
            duration_ms=self._duration_ms(started),
            metadata={"mode": "cli"},
        )

    @classmethod
    def _build_targets(cls, context: CollectorContext, scan_dir: Path) -> list[Path]:
        if context.run_kind == "baseline" or not context.changed_files:
            has_js_ts = any(
                candidate.is_file() and candidate.suffix.lower() in cls._JS_TS_EXTENSIONS
                for candidate in scan_dir.rglob("*")
            )
            return [scan_dir] if has_js_ts else []

        targets: list[Path] = []
        for relative_path in context.changed_files:
            candidate = scan_dir / relative_path
            if candidate.suffix.lower() in cls._JS_TS_EXTENSIONS and candidate.is_file():
                targets.append(candidate)
        return targets

    @staticmethod
    def _map_severity(rule_id: str, severity: int) -> str:
        if severity == 1:
            return "LOW"
        if severity == 2 and rule_id.startswith("security/"):
            return "HIGH"
        if severity == 2:
            return "MEDIUM"
        return "LOW"

    @classmethod
    def _parse_cli_output(cls, stdout: str) -> list[dict[str, object]]:
        if not stdout.strip():
            return []
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []

        findings: list[dict[str, object]] = []
        for file_result in payload:
            if not isinstance(file_result, dict):
                continue
            file_path = str(file_result.get("filePath", ""))
            messages = file_result.get("messages", [])
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict):
                    continue
                rule_id = str(message.get("ruleId", ""))
                severity_raw = message.get("severity", 1)
                severity_int = severity_raw if isinstance(severity_raw, int) else 1
                line_raw = message.get("line", 0)
                end_line_raw = message.get("endLine", line_raw)
                column_raw = message.get("column", 0)

                findings.append(
                    {
                        "rule_id": rule_id,
                        "path": file_path,
                        "line": line_raw if isinstance(line_raw, int) else 0,
                        "end_line": end_line_raw if isinstance(end_line_raw, int) else 0,
                        "column": column_raw if isinstance(column_raw, int) else 0,
                        "severity": cls._map_severity(rule_id, severity_int),
                        "message": str(message.get("message", "")),
                    }
                )
        return findings

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
