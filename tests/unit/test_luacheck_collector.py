from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.luacheck import LuacheckCollector
from agent_review.config import Settings


class _StubProc:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout.encode("utf-8"), self._stderr.encode("utf-8")


def _context(local_path: Path, changed_files: list[str]) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=changed_files,
        github_client=None,
        local_path=str(local_path),
    )


@pytest.mark.asyncio
async def test_tc_lua_001_mode_disabled_returns_skipped(tmp_path: Path) -> None:
    """TC-LUA-001: mode disabled -> skipped."""
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"luacheck_mode": "disabled"})
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=[]))

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_lua_002_no_lua_files_returns_skipped(tmp_path: Path) -> None:
    """TC-LUA-002: no .lua files -> skipped."""
    _ = (tmp_path / "README.md").write_text("hello")

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"luacheck_mode": "cli"})
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=["README.md"]))

    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_lua_files"


@pytest.mark.asyncio
async def test_tc_lua_003_parse_w111_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TC-LUA-003: parse plain output with W111 warning."""
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "main.lua").write_text("foo = 1\n")
    output_line = (
        f"{tmp_path / 'src' / 'main.lua'}:10:5-10: (W111) setting non-standard global variable foo"
    )

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> _StubProc:
        _ = args, kwargs
        return _StubProc(returncode=1, stdout=output_line)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"luacheck_mode": "cli"})
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=["src/main.lua"]))

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    finding = result.raw_findings[0]
    assert finding == {
        "rule_id": "W111",
        "path": "src/main.lua",
        "line": 10,
        "end_line": None,
        "severity": "INFO",
        "message": "setting non-standard global variable foo",
        "snippet": "",
        "fingerprint": "",
        "category": "quality.static-analysis",
        "cwe": [],
        "precision": "unknown",
        "tool_name": "luacheck",
    }


def test_tc_lua_004_e0_codes_map_to_error() -> None:
    """TC-LUA-004: E0* codes -> ERROR severity."""
    findings = LuacheckCollector._parse_cli_output(
        "src/main.lua:1:1-1: (E011) syntax error near 'end'"
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "ERROR"
    assert findings[0]["category"] == "quality.syntax-error"


def test_tc_lua_005_w0_codes_map_to_warning() -> None:
    """TC-LUA-005: W0* codes -> WARNING severity."""
    findings = LuacheckCollector._parse_cli_output(
        "src/main.lua:2:1-3: (W021) accessing undefined variable foo"
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "WARNING"


def test_tc_lua_006_w1_codes_map_to_info() -> None:
    """TC-LUA-006: W1* codes -> INFO severity."""
    findings = LuacheckCollector._parse_cli_output(
        "src/main.lua:3:1-3: (W111) setting non-standard global variable foo"
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "INFO"


@pytest.mark.asyncio
async def test_tc_lua_007_config_flag_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TC-LUA-007: custom config path passes --config flag."""
    _ = (tmp_path / "main.lua").write_text("x = 1\n")
    captured_cmd: list[str] = []

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> _StubProc:
        _ = kwargs
        captured_cmd.extend(cast(tuple[str, ...], args))
        return _StubProc(returncode=0, stdout="")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate(
            {
                "luacheck_mode": "cli",
                "luacheck_config_path": "/tmp/custom.luacheckrc",
            }
        )
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=["main.lua"]))

    assert result.status == "success"
    assert "--config" in captured_cmd
    config_index = captured_cmd.index("--config")
    assert captured_cmd[config_index + 1] == "/tmp/custom.luacheckrc"


@pytest.mark.asyncio
async def test_tc_lua_008_luacheck_not_installed_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TC-LUA-008: FileNotFoundError from luacheck returns failure."""
    _ = (tmp_path / "main.lua").write_text("x = 1\n")

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> _StubProc:
        _ = args, kwargs
        raise FileNotFoundError("luacheck not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"luacheck_mode": "cli"})
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=["main.lua"]))

    assert result.status == "failure"
    assert "luacheck not found" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_lua_009_clean_output_returns_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TC-LUA-009: clean output (exit 0) returns success with empty findings."""
    _ = (tmp_path / "main.lua").write_text("local x = 1\n")

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> _StubProc:
        _ = args, kwargs
        return _StubProc(returncode=0, stdout="")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"luacheck_mode": "cli"})
        collector = LuacheckCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path, changed_files=["main.lua"]))

    assert result.status == "success"
    assert result.raw_findings == []
