from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from pydantic import SecretStr

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.semgrep import SemgrepCollector
from agent_review.config import Settings

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


class StubGitHubClient:
    pass


@pytest.mark.asyncio
async def test_semgrep_parses_findings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/deployments/o/r/findings"
        return httpx.Response(
            200,
            json={
                "findings": [
                    {
                        "check_id": "python.lang.security.audit",
                        "path": "src/auth.py",
                        "start": {"line": 12},
                        "extra": {"severity": "ERROR", "message": "Issue"},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = Settings.model_validate(
            {
                "semgrep_mode": "app",
                "semgrep_app_token": SecretStr("token"),
            }
        )
        collector = SemgrepCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["rule_id"] == "python.lang.security.audit"


@pytest.mark.asyncio
async def test_semgrep_api_error_returns_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(500, json={"error": "oops"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = Settings.model_validate(
            {
                "semgrep_mode": "app",
                "semgrep_app_token": SecretStr("token"),
            }
        )
        collector = SemgrepCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "failure"
    assert "500" in (result.error or "")


@pytest.mark.asyncio
async def test_semgrep_disabled_returns_skipped() -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"semgrep_mode": "disabled"})
        collector = SemgrepCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            pr_number=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            changed_files=[],
            github_client=cast("GitHubClient", StubGitHubClient()),
        )

        result = await collector.collect(context)

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


def test_parse_cli_output_empty() -> None:
    assert SemgrepCollector._parse_cli_output("") == []
    assert SemgrepCollector._parse_cli_output("not json") == []


def test_parse_cli_output_no_results() -> None:
    output = json.dumps({"version": "1.0", "results": [], "errors": []})
    assert SemgrepCollector._parse_cli_output(output) == []


def test_parse_cli_output_with_findings() -> None:
    output = json.dumps(
        {
            "version": "1.0",
            "results": [
                {
                    "check_id": "python.lang.security.audit.subprocess-shell-true",
                    "path": "src/utils.py",
                    "start": {"line": 42, "col": 5, "offset": 1234},
                    "end": {"line": 42, "col": 58, "offset": 1287},
                    "extra": {
                        "severity": "ERROR",
                        "message": "Found subprocess call with shell=True",
                        "lines": "    subprocess.run(cmd, shell=True)",
                        "fingerprint": "abc123",
                        "is_ignored": False,
                        "metadata": {
                            "category": "security",
                            "cwe": ["CWE-78: OS Command Injection"],
                            "confidence": "HIGH",
                        },
                    },
                }
            ],
        }
    )
    findings = SemgrepCollector._parse_cli_output(output)
    assert len(findings) == 1
    f = findings[0]
    assert f["rule_id"] == "python.lang.security.audit.subprocess-shell-true"
    assert f["path"] == "src/utils.py"
    assert f["line"] == 42
    assert f["end_line"] == 42
    assert f["severity"] == "ERROR"
    assert f["message"] == "Found subprocess call with shell=True"
    assert f["snippet"] == "    subprocess.run(cmd, shell=True)"
    assert f["fingerprint"] == "abc123"
    assert f["category"] == "security"
    assert f["cwe"] == ["CWE-78: OS Command Injection"]
    assert f["confidence"] == "HIGH"


def test_parse_cli_output_skips_ignored_findings() -> None:
    output = json.dumps(
        {
            "results": [
                {
                    "check_id": "rule-1",
                    "path": "a.py",
                    "start": {"line": 1},
                    "end": {"line": 1},
                    "extra": {
                        "severity": "WARNING",
                        "message": "suppressed",
                        "is_ignored": True,
                        "metadata": {},
                    },
                },
                {
                    "check_id": "rule-2",
                    "path": "b.py",
                    "start": {"line": 5},
                    "end": {"line": 5},
                    "extra": {
                        "severity": "ERROR",
                        "message": "not suppressed",
                        "is_ignored": False,
                        "metadata": {},
                    },
                },
            ]
        }
    )
    findings = SemgrepCollector._parse_cli_output(output)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "rule-2"


def test_build_command_with_severity_filter() -> None:
    settings = Settings.model_validate(
        {
            "semgrep_mode": "cli",
            "semgrep_rules_path": "/opt/semgrep-rules",
            "semgrep_severity_filter": ["CRITICAL", "ERROR"],
        }
    )
    collector = SemgrepCollector(settings=settings, http_client=cast("httpx.AsyncClient", None))
    cmd = collector._build_command("/opt/semgrep-rules", [], Path("/tmp/repo"))
    assert "--severity" in cmd
    sev_indices = [i for i, v in enumerate(cmd) if v == "--severity"]
    severities = [cmd[i + 1] for i in sev_indices]
    assert "CRITICAL" in severities
    assert "ERROR" in severities
    assert str(Path("/tmp/repo")) in cmd


def test_build_command_scans_only_changed_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("pass")
    settings = Settings.model_validate(
        {
            "semgrep_mode": "cli",
            "semgrep_rules_path": "/opt/semgrep-rules",
            "semgrep_severity_filter": ["ERROR"],
        }
    )
    collector = SemgrepCollector(settings=settings, http_client=cast("httpx.AsyncClient", None))
    cmd = collector._build_command("/opt/semgrep-rules", ["src/app.py"], tmp_path)
    assert str(tmp_path / "src" / "app.py") in cmd


def test_find_repo_root_single_dir(tmp_path: Path) -> None:
    subdir = tmp_path / "owner-repo-abc123"
    subdir.mkdir()
    (tmp_path / "repo.tar.gz").write_bytes(b"")
    result = SemgrepCollector._find_repo_root(str(tmp_path))
    assert result == subdir


def test_find_repo_root_fallback(tmp_path: Path) -> None:
    result = SemgrepCollector._find_repo_root(str(tmp_path))
    assert result == tmp_path
