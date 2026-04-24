from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.observability import get_logger

if TYPE_CHECKING:
    import httpx

    from agent_review.config import Settings

logger = get_logger(__name__)


class LuacheckCollector(AbstractCollector):
    name = "luacheck"

    _LINE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+)-(?P<end_col>\d+):"
        r" \((?P<code>[A-Z]\d+)\) (?P<message>.+)$"
    )

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client

    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            mode = self._settings.luacheck_mode
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
                metadata={"mode": self._settings.luacheck_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        scan_dir = Path(context.local_path or ".")
        if not scan_dir.is_dir():
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=f"Local path does not exist: {context.local_path}",
                metadata={"mode": "cli"},
            )

        targets = self._detect_lua_targets(scan_dir, context.changed_files)
        if not targets:
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "reason": "no_lua_files"},
            )

        cmd: list[str] = [
            "luacheck",
            "--formatter",
            "plain",
            "--codes",
            "--ranges",
            "--no-color",
        ]
        if self._settings.luacheck_config_path:
            cmd.extend(["--config", self._settings.luacheck_config_path])
        cmd.extend(str(target) for target in targets)

        logger.info(
            "luacheck_cli_start",
            repo=context.repo,
            head_sha=context.head_sha,
            file_count=len(targets),
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
                error=f"luacheck exited with code {proc.returncode}: {stderr_text[:500]}",
                metadata={"mode": "cli"},
            )

        raw_findings = self._parse_cli_output(stdout_text)
        scan_dir_prefix = str(scan_dir.resolve()) + "/"
        for finding in raw_findings:
            finding_path = str(finding.get("path", ""))
            resolved_path = str((scan_dir / finding_path).resolve())
            if finding_path.startswith(scan_dir_prefix):
                finding["path"] = finding_path[len(scan_dir_prefix) :]
            elif resolved_path.startswith(scan_dir_prefix):
                finding["path"] = resolved_path[len(scan_dir_prefix) :]

        logger.info(
            "luacheck_cli_done",
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
    def _detect_lua_targets(cls, scan_dir: Path, changed_files: list[str]) -> list[Path]:
        if changed_files:
            targets: list[Path] = []
            for file_path in changed_files:
                if not file_path.lower().endswith(".lua"):
                    continue
                candidate = scan_dir / file_path
                if candidate.exists() and candidate.is_file():
                    targets.append(candidate)
            return targets
        return [path for path in scan_dir.rglob("*.lua") if path.is_file()]

    @classmethod
    def _parse_cli_output(cls, stdout: str) -> list[dict[str, object]]:
        if not stdout.strip():
            return []

        findings: list[dict[str, object]] = []
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = cls._LINE_RE.match(line)
            if match is None:
                continue

            code = match.group("code")
            severity = cls._map_code_to_severity(code)
            category = "quality.syntax-error" if code.startswith("E") else "quality.static-analysis"
            findings.append(
                {
                    "rule_id": code,
                    "path": match.group("path"),
                    "line": int(match.group("line")),
                    "end_line": None,
                    "severity": severity,
                    "message": match.group("message"),
                    "snippet": "",
                    "fingerprint": "",
                    "category": category,
                    "cwe": [],
                    "precision": "unknown",
                    "tool_name": "luacheck",
                }
            )

        return findings

    @staticmethod
    def _map_code_to_severity(code: str) -> str:
        if code.startswith("E0"):
            return "ERROR"
        if code.startswith("W0"):
            return "WARNING"
        if code.startswith("W1"):
            return "INFO"
        if code.startswith("W2"):
            return "WARNING"
        if code.startswith("W3"):
            return "INFO"
        if code.startswith("W4") or code.startswith("W5"):
            return "INFO"
        if code.startswith("W6"):
            return "INFO"
        return "WARNING"

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
