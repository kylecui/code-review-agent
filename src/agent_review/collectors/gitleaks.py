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


class GitleaksCollector(AbstractCollector):
    name: ClassVar[str] = "gitleaks"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings: Settings = settings
        self._http: httpx.AsyncClient = http_client
        self._sarif_adapter: SarifAdapter = SarifAdapter()

    @override
    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        report_path: Path | None = None
        try:
            mode = self._settings.gitleaks_mode
            if mode == "disabled":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode},
                )

            scan_dir = Path(context.local_path) if context.local_path else Path(".")

            with tempfile.NamedTemporaryFile(suffix=".sarif", delete=False) as tmpfile:
                report_path = Path(tmpfile.name)

            cmd = [
                "gitleaks",
                "detect",
                "--source",
                str(scan_dir),
                "--report-format",
                "sarif",
                "--report-path",
                str(report_path),
                "--no-git",
                "--exit-code",
                "0",
            ]
            if self._settings.gitleaks_config_path:
                cmd.extend(["--config", self._settings.gitleaks_config_path])

            logger.info("gitleaks_cli_start", repo=context.repo, head_sha=context.head_sha)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            _, stderr_bytes = await proc.communicate()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"gitleaks exited with code {proc.returncode}: {stderr_text[:500]}",
                    metadata={"mode": mode},
                )

            raw_findings = self._sarif_adapter.parse_file(report_path)
            scan_dir_prefix = str(scan_dir) + "/"
            for finding in raw_findings:
                path = str(finding.get("path", ""))
                if path.startswith(scan_dir_prefix):
                    finding["path"] = path[len(scan_dir_prefix) :]

            logger.info("gitleaks_cli_done", finding_count=len(raw_findings))
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
                metadata={"mode": self._settings.gitleaks_mode},
            )
        finally:
            if report_path is not None:
                report_path.unlink(missing_ok=True)

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
