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


class GolangciLintCollector(AbstractCollector):
    name: ClassVar[str] = "golangci_lint"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings: Settings = settings
        self._http: httpx.AsyncClient = http_client
        self._sarif_adapter: SarifAdapter = SarifAdapter()

    @override
    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        report_path: Path | None = None
        try:
            mode = self._settings.golangci_lint_mode
            if mode == "disabled":
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode},
                )

            scan_dir = Path(context.local_path) if context.local_path else Path(".")
            if not self._has_go_files(context.changed_files, scan_dir):
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"mode": mode, "reason": "no_go_files"},
                )

            cmd = [
                "golangci-lint",
                "run",
                "--out-format",
                "sarif",
                "--timeout",
                f"{self._settings.golangci_lint_timeout}s",
                "./...",
            ]
            if self._settings.golangci_lint_config_path:
                cmd.extend(["--config", self._settings.golangci_lint_config_path])

            logger.info("golangci_lint_cli_start", repo=context.repo, head_sha=context.head_sha)

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
                    error=(
                        f"golangci-lint exited with code {proc.returncode}: {stderr_text[:500]}"
                    ),
                    metadata={"mode": mode},
                )

            with tempfile.NamedTemporaryFile(suffix=".sarif", delete=False) as tmpfile:
                report_path = Path(tmpfile.name)
                _ = report_path.write_text(stdout_text, encoding="utf-8")

            raw_findings = self._sarif_adapter.parse_file(report_path)
            scan_dir_prefix = str(scan_dir) + "/"
            for finding in raw_findings:
                path = str(finding.get("path", ""))
                if path.startswith(scan_dir_prefix):
                    finding["path"] = path[len(scan_dir_prefix) :]

            logger.info("golangci_lint_cli_done", finding_count=len(raw_findings))
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
                metadata={"mode": self._settings.golangci_lint_mode},
            )
        finally:
            if report_path is not None:
                report_path.unlink(missing_ok=True)

    @staticmethod
    def _has_go_files(changed_files: list[str], scan_dir: Path) -> bool:
        if changed_files:
            return any(path.endswith(".go") for path in changed_files)
        return any(scan_dir.rglob("*.go"))

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
