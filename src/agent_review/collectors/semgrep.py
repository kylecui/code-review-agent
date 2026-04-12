from __future__ import annotations

import asyncio
import json
import shutil
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
                return await self._collect_cli(context, started)

            return await self._collect_app(context, started)
        except Exception as exc:
            return CollectorResult(
                collector_name=self.name,
                status="failure",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error=str(exc),
                metadata={"mode": self._settings.semgrep_mode},
            )

    async def _collect_cli(self, context: CollectorContext, started: float) -> CollectorResult:
        """Run semgrep CLI with community rules against the PR's changed files."""
        rules_path = self._settings.semgrep_rules_path

        tmpdir = tempfile.mkdtemp(prefix="semgrep_scan_")
        try:
            await self._download_repo(context, tmpdir)
            scan_dir = self._find_repo_root(tmpdir)
            cmd = self._build_command(rules_path, context.changed_files, scan_dir)
            logger.info(
                "semgrep_cli_start",
                repo=context.repo,
                head_sha=context.head_sha,
                file_count=len(context.changed_files),
                rules_path=rules_path,
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

            # semgrep exits with 0=no findings, 1=findings found, other=error
            if proc.returncode not in (0, 1):
                logger.warning(
                    "semgrep_cli_error",
                    returncode=proc.returncode,
                    stderr=stderr_text[:2000],
                )
                return CollectorResult(
                    collector_name=self.name,
                    status="failure",
                    raw_findings=[],
                    duration_ms=self._duration_ms(started),
                    error=f"semgrep exited with code {proc.returncode}: {stderr_text[:500]}",
                    metadata={"mode": "cli"},
                )

            raw_findings = self._parse_cli_output(stdout_text)
            logger.info(
                "semgrep_cli_done",
                finding_count=len(raw_findings),
                duration_ms=self._duration_ms(started),
            )

            return CollectorResult(
                collector_name=self.name,
                status="success",
                raw_findings=raw_findings,
                duration_ms=self._duration_ms(started),
                metadata={"mode": "cli", "rules_path": rules_path},
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _download_repo(self, context: CollectorContext, tmpdir: str) -> None:
        """Download and extract the repo at head_sha via GitHub tarball API."""
        token = await context.github_client._get_token()
        tarball_url = f"https://api.github.com/repos/{context.repo}/tarball/{context.head_sha}"
        response = await self._http.get(
            tarball_url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            follow_redirects=True,
        )
        response.raise_for_status()

        tarball_path = Path(tmpdir) / "repo.tar.gz"
        tarball_path.write_bytes(response.content)

        proc = await asyncio.create_subprocess_exec(
            "tar",
            "xzf",
            str(tarball_path),
            "-C",
            tmpdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    @staticmethod
    def _find_repo_root(tmpdir: str) -> Path:
        """GitHub tarballs extract into a single subdirectory like 'owner-repo-sha/'."""
        entries = list(Path(tmpdir).iterdir())
        dirs = [entry for entry in entries if entry.is_dir()]
        if len(dirs) == 1:
            return dirs[0]
        return Path(tmpdir)

    def _build_command(
        self,
        rules_path: str,
        changed_files: list[str],
        scan_dir: Path,
    ) -> list[str]:
        cmd = [
            "semgrep",
            "scan",
            "--config",
            rules_path,
            "--json",
            "--quiet",
            "-j",
            "2",
            "--timeout",
            "10",
            "--max-target-bytes",
            "1000000",
        ]

        for sev in self._settings.semgrep_severity_filter:
            cmd.extend(["--severity", sev])

        if changed_files:
            for file_path in changed_files:
                full_path = scan_dir / file_path
                if full_path.exists():
                    cmd.append(str(full_path))
            if cmd[-1] == "1000000" or cmd[-1].startswith("--"):
                cmd.append(str(scan_dir))
        else:
            cmd.append(str(scan_dir))

        return cmd

    @staticmethod
    def _parse_cli_output(stdout: str) -> list[dict[str, object]]:
        """Parse semgrep JSON output into our raw_findings format."""
        if not stdout.strip():
            return []
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        results = output.get("results", [])
        if not isinstance(results, list):
            return []

        raw_findings: list[dict[str, object]] = []
        for result in results:
            if not isinstance(result, dict):
                continue

            extra = result.get("extra", {})
            if not isinstance(extra, dict):
                extra = {}
            if extra.get("is_ignored", False):
                continue

            start = result.get("start", {})
            if not isinstance(start, dict):
                start = {}
            end = result.get("end", {})
            if not isinstance(end, dict):
                end = {}

            metadata = extra.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            raw_findings.append(
                {
                    "rule_id": str(result.get("check_id", "")),
                    "path": str(result.get("path", "")),
                    "line": int(start.get("line", 0)) if isinstance(start.get("line"), int) else 0,
                    "end_line": int(end.get("line", 0)) if isinstance(end.get("line"), int) else 0,
                    "severity": str(extra.get("severity", "")),
                    "message": str(extra.get("message", "")),
                    "snippet": str(extra.get("lines", "")),
                    "fingerprint": str(extra.get("fingerprint", "")),
                    "category": str(metadata.get("category", "")),
                    "cwe": metadata.get("cwe", []),
                    "confidence": str(metadata.get("confidence", "")),
                }
            )

        return raw_findings

    async def _collect_app(self, context: CollectorContext, started: float) -> CollectorResult:
        """Collect findings from Semgrep Cloud API (legacy mode)."""
        token = self._settings.semgrep_app_token
        if token is None or not token.get_secret_value():
            return CollectorResult(
                collector_name=self.name,
                status="skipped",
                raw_findings=[],
                duration_ms=self._duration_ms(started),
                error="Semgrep app token missing",
                metadata={"mode": "app"},
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
                metadata={"mode": "app"},
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
            metadata={"mode": "app"},
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
