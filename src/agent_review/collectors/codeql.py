from __future__ import annotations

import asyncio
import shutil
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


class CodeQLCollector(AbstractCollector):
    name: ClassVar[str] = "codeql"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings: Settings = settings
        self._http: httpx.AsyncClient = http_client
        self._sarif_adapter: SarifAdapter = SarifAdapter()

    @override
    async def collect(self, context: CollectorContext) -> CollectorResult:
        started = time.perf_counter()
        report_path: Path | None = None
        database_dir: str | None = None

        codeql_enabled = bool(
            getattr(
                self._settings,
                "codeql_enabled",
                getattr(self._settings, "codeql_mode", "disabled") != "disabled",
            )
        )
        codeql_path = str(getattr(self._settings, "codeql_path", "codeql"))
        codeql_timeout = int(getattr(self._settings, "codeql_timeout", 1800))

        try:
            if not codeql_enabled:
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={"enabled": False},
                )

            if context.local_path is None:
                return CollectorResult(
                    collector_name=self.name,
                    status="skipped",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    metadata={
                        "enabled": True,
                        "note": "local_path is required for CodeQL CLI scan",
                    },
                )

            scan_dir = Path(context.local_path)
            if not scan_dir.is_dir():
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"Local path does not exist: {context.local_path}",
                    metadata={"enabled": True},
                )

            with tempfile.NamedTemporaryFile(suffix=".sarif", delete=False) as tmpfile:
                report_path = Path(tmpfile.name)
            database_dir = tempfile.mkdtemp(prefix="codeql_db_")
            database_path = Path(database_dir) / "db"

            create_cmd = [
                codeql_path,
                "database",
                "create",
                str(database_path),
                f"--source-root={scan_dir}",
                "--language=python",
                "--overwrite",
            ]
            analyze_cmd = [
                codeql_path,
                "database",
                "analyze",
                str(database_path),
                "--format=sarif-latest",
                f"--output={report_path}",
            ]

            logger.info("codeql_cli_start", repo=context.repo, head_sha=context.head_sha)

            create_proc = await asyncio.create_subprocess_exec(
                *create_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            try:
                _, create_stderr = await asyncio.wait_for(
                    create_proc.communicate(), timeout=float(codeql_timeout)
                )
            except TimeoutError:
                create_proc.kill()
                _ = await create_proc.communicate()
                return CollectorResult(
                    collector_name=self.name,
                    status="timeout",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"codeql database create timed out after {codeql_timeout}s",
                    metadata={"enabled": True},
                )

            if create_proc.returncode != 0:
                create_stderr_text = create_stderr.decode("utf-8", errors="replace")
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=(
                        f"codeql database create exited with code {create_proc.returncode}: "
                        f"{create_stderr_text[:500]}"
                    ),
                    metadata={"enabled": True},
                )

            analyze_proc = await asyncio.create_subprocess_exec(
                *analyze_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scan_dir),
            )
            try:
                _, analyze_stderr = await asyncio.wait_for(
                    analyze_proc.communicate(), timeout=float(codeql_timeout)
                )
            except TimeoutError:
                analyze_proc.kill()
                _ = await analyze_proc.communicate()
                return CollectorResult(
                    collector_name=self.name,
                    status="timeout",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"codeql database analyze timed out after {codeql_timeout}s",
                    metadata={"enabled": True},
                )

            if analyze_proc.returncode != 0:
                analyze_stderr_text = analyze_stderr.decode("utf-8", errors="replace")
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=(
                        f"codeql database analyze exited with code {analyze_proc.returncode}: "
                        f"{analyze_stderr_text[:500]}"
                    ),
                    metadata={"enabled": True},
                )

            parsed_findings = self._sarif_adapter.parse_file(report_path)
            normalized_findings: list[dict[str, object]] = []
            scan_dir_prefix = str(scan_dir) + "/"
            for finding in parsed_findings:
                finding_path = str(finding.get("path", ""))
                if finding_path.startswith(scan_dir_prefix):
                    finding_path = finding_path[len(scan_dir_prefix) :]
                normalized_findings.append(
                    {
                        "rule_id": str(finding.get("rule_id", "")),
                        "path": finding_path,
                        "line": finding.get("line", 0),
                        "end_line": finding.get("end_line"),
                        "severity": str(finding.get("severity", "")),
                        "message": str(finding.get("message", "")),
                        "snippet": str(finding.get("snippet", "")),
                        "cwe": finding.get("cwe", []),
                        "precision": str(finding.get("precision", "")),
                        "category": str(finding.get("category", "")),
                    }
                )

            logger.info("codeql_cli_done", finding_count=len(normalized_findings))
            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=normalized_findings,
                duration_ms=self._duration_ms(started),
                metadata={"enabled": True},
            )
        except Exception as exc:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
                metadata={"enabled": codeql_enabled},
            )
        finally:
            if report_path is not None:
                report_path.unlink(missing_ok=True)
            if database_dir is not None:
                shutil.rmtree(database_dir, ignore_errors=True)

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
