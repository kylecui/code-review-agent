from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.normalize.sarif_adapter import SarifAdapter
from agent_review.observability import get_logger

if TYPE_CHECKING:
    import httpx

    from agent_review.config import Settings

logger = get_logger(__name__)


class CppcheckCollector(AbstractCollector):
    name: ClassVar[str] = "cppcheck"

    _settings: Settings
    _http: httpx.AsyncClient
    _sarif: SarifAdapter

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._http = http_client
        self._sarif = SarifAdapter()

    @override
    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        try:
            mode = self._settings.cppcheck_mode
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
                metadata={"mode": self._settings.cppcheck_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        scan_dir = Path(context.local_path) if context.local_path is not None else None

        if not self._has_cpp_targets(context, scan_dir):
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "reason": "no_cpp_files"},
            )

        if scan_dir is None or not scan_dir.is_dir():
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=f"Local path does not exist: {context.local_path}",
                metadata={"mode": "cli"},
            )

        with tempfile.NamedTemporaryFile(prefix="cppcheck_", suffix=".sarif", delete=False) as tmp:
            sarif_path = Path(tmp.name)

        try:
            cmd = [
                "cppcheck",
                f"--enable={self._settings.cppcheck_enable}",
                "--inconclusive",
                "--force",
                *[f"--suppress={value}" for value in self._settings.cppcheck_suppressions],
                f"--output-file={sarif_path}",
                "--output-format=sarif",
                str(scan_dir),
            ]
            logger.info("cppcheck_cli_start", repo=context.repo, head_sha=context.head_sha)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            _stdout_bytes, stderr_bytes = await proc.communicate()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode not in (0, 1):
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"cppcheck exited with code {proc.returncode}: {stderr_text[:500]}",
                    metadata={"mode": "cli"},
                )

            raw_findings = self._sarif.parse_file(sarif_path)
            scan_dir_prefix = f"{scan_dir}/"
            for finding in raw_findings:
                path = str(finding.get("path", ""))
                if path.startswith(scan_dir_prefix):
                    finding["path"] = path[len(scan_dir_prefix) :]

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=raw_findings,
                duration_ms=self._duration_ms(started),
                metadata={
                    "mode": "cli",
                    "enable": self._settings.cppcheck_enable,
                    "suppressions": self._settings.cppcheck_suppressions,
                },
            )
        except FileNotFoundError:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="cppcheck is not installed or not found in PATH",
                metadata={"mode": "cli"},
            )
        finally:
            sarif_path.unlink(missing_ok=True)

    @staticmethod
    def _has_cpp_targets(context: CollectorContext, scan_dir: Path | None) -> bool:
        extensions = (".c", ".h", ".cpp", ".cc", ".cxx")
        if any(file_path.lower().endswith(extensions) for file_path in context.changed_files):
            return True
        if scan_dir is None or not scan_dir.is_dir():
            return False
        return (
            any(scan_dir.rglob("*.c"))
            or any(scan_dir.rglob("*.h"))
            or any(scan_dir.rglob("*.cpp"))
            or any(scan_dir.rglob("*.cc"))
            or any(scan_dir.rglob("*.cxx"))
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
