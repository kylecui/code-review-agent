from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.eslint_security import EslintSecurityCollector
from agent_review.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


class _FakeProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _context(local_path: Path, changed_files: list[str], run_kind: str = "pr") -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=changed_files,
        github_client=None,
        run_kind=run_kind,
        pr_number=1,
        base_sha="b" * 40,
        local_path=str(local_path),
    )


@pytest.mark.asyncio
async def test_tc_esl_001_disabled_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "disabled"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, []))
    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_esl_002_no_js_ts_files_returns_skipped(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello")

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, [], run_kind="baseline"))
    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_js_ts_files"


@pytest.mark.asyncio
async def test_tc_esl_003_pr_mode_filters_changed_js_ts_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    js_file = tmp_path / "src" / "a.ts"
    py_file = tmp_path / "src" / "b.py"
    js_file.write_text("const x = 1")
    py_file.write_text("print('x')")

    captured_cmd: list[str] = []

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        captured_cmd.extend(cmd)
        return _FakeProcess(returncode=0, stdout="[]")

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["src/a.ts", "src/b.py"]))

    assert result.status == "success"
    assert str(js_file) in captured_cmd
    assert str(py_file) not in captured_cmd


@pytest.mark.asyncio
async def test_tc_esl_004_baseline_mode_passes_scan_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.js").write_text("console.log('x')")
    captured_cmd: list[str] = []

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        captured_cmd.extend(cmd)
        return _FakeProcess(returncode=0, stdout="[]")

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["index.js"], run_kind="baseline"))

    assert result.status == "success"
    assert str(tmp_path) in captured_cmd


@pytest.mark.asyncio
async def test_tc_esl_005_parses_output_and_maps_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.js").write_text("x")
    payload = json.dumps(
        [
            {
                "filePath": str(tmp_path / "src" / "a.js"),
                "messages": [
                    {
                        "ruleId": "security/detect-object-injection",
                        "severity": 2,
                        "message": "security issue",
                        "line": 3,
                        "endLine": 3,
                        "column": 10,
                    },
                    {
                        "ruleId": "no-console",
                        "severity": 2,
                        "message": "console",
                        "line": 4,
                        "endLine": 4,
                        "column": 1,
                    },
                    {
                        "ruleId": "semi",
                        "severity": 1,
                        "message": "warn",
                        "line": 5,
                        "endLine": 5,
                        "column": 2,
                    },
                ],
            }
        ]
    )

    async def _fake_create_subprocess_exec(*_: str, **__: object) -> _FakeProcess:
        return _FakeProcess(returncode=1, stdout=payload)

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["src/a.js"]))

    assert result.status == "success"
    severities = [cast("str", f["severity"]) for f in result.raw_findings]
    assert severities == ["HIGH", "MEDIUM", "LOW"]


@pytest.mark.asyncio
async def test_tc_esl_006_cli_error_returns_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.js").write_text("x")

    async def _fake_create_subprocess_exec(*_: str, **__: object) -> _FakeProcess:
        return _FakeProcess(returncode=2, stderr="bad command")

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["index.js"]))

    assert result.status == "failure"
    assert "eslint exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_esl_007_invalid_json_output_returns_empty_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.ts").write_text("x")

    async def _fake_create_subprocess_exec(*_: str, **__: object) -> _FakeProcess:
        return _FakeProcess(returncode=0, stdout="not-json")

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["index.ts"]))

    assert result.status == "success"
    assert result.raw_findings == []


@pytest.mark.asyncio
async def test_tc_esl_008_strips_scan_dir_prefix_from_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.js").write_text("x")
    payload = json.dumps(
        [
            {
                "filePath": str(tmp_path / "src" / "x.js"),
                "messages": [
                    {
                        "ruleId": "security/no-eval",
                        "severity": 2,
                        "message": "issue",
                        "line": 1,
                        "endLine": 1,
                        "column": 1,
                    }
                ],
            }
        ]
    )

    async def _fake_create_subprocess_exec(*_: str, **__: object) -> _FakeProcess:
        return _FakeProcess(returncode=1, stdout=payload)

    monkeypatch.setattr(
        "agent_review.collectors.eslint_security.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"eslint_security_mode": "cli"})
        collector = EslintSecurityCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, ["src/x.js"]))

    assert result.status == "success"
    assert result.raw_findings[0]["path"] == "src/x.js"
