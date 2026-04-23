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


class SpotBugsCollector(AbstractCollector):
    name: ClassVar[str] = "spotbugs"

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
            mode = self._settings.spotbugs_mode
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
                metadata={"mode": self._settings.spotbugs_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        scan_dir = Path(context.local_path) if context.local_path is not None else None

        if not self._has_java_targets(context, scan_dir):
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "reason": "no_java_files"},
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

        has_compiled_artifacts = any(scan_dir.rglob("*.class")) or any(scan_dir.rglob("*.jar"))
        if not has_compiled_artifacts:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="No compiled Java artifacts (*.class or *.jar) found in scan directory",
                metadata={"mode": "cli"},
            )

        with tempfile.NamedTemporaryFile(prefix="spotbugs_", suffix=".sarif", delete=False) as tmp:
            sarif_path = Path(tmp.name)

        try:
            cmd = [
                self._settings.spotbugs_path,
                "-textui",
                "-sarif",
                f"-effort:{self._settings.spotbugs_effort}",
                "-low",
                "-pluginList",
                self._settings.spotbugs_findsecbugs_plugin,
                "-output",
                str(sarif_path),
                str(scan_dir),
            ]
            logger.info("spotbugs_cli_start", repo=context.repo, head_sha=context.head_sha)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            _stdout_bytes, stderr_bytes = await proc.communicate()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"spotbugs exited with code {proc.returncode}: {stderr_text[:500]}",
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
                    "effort": self._settings.spotbugs_effort,
                },
            )
        finally:
            sarif_path.unlink(missing_ok=True)

    @staticmethod
    def _has_java_targets(context: CollectorContext, scan_dir: Path | None) -> bool:
        if any(file_path.lower().endswith(".java") for file_path in context.changed_files):
            return True
        if scan_dir is None or not scan_dir.is_dir():
            return False
        return any(scan_dir.rglob("*.java"))

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
