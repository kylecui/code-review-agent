from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.roslyn import RoslynCollector
from agent_review.config import Settings


class _FakeProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _context(local_path: Path) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=[],
        github_client=None,
        run_kind="baseline",
        pr_number=1,
        base_sha="b" * 40,
        local_path=str(local_path),
    )


@pytest.mark.asyncio
async def test_tc_ros_001_disabled_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "disabled"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))
    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_ros_002_no_cs_files_returns_skipped(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("no csharp")

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_csharp_files"


@pytest.mark.asyncio
async def test_tc_ros_003_missing_project_returns_failure(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.cs").write_text("class A {}")

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "failure"
    assert "No .csproj or .sln file found" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_ros_004_parses_output_and_maps_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.csproj").write_text("<Project />")
    (tmp_path / "Program.cs").write_text("class Program {}")

    payload = {
        "diagnostics": [
            {
                "id": "CS0168",
                "severity": "Error",
                "message": "error",
                "location": {"path": str(tmp_path / "Program.cs"), "line": 11},
            },
            {
                "id": "CA2100",
                "severity": "Warning",
                "message": "security warning",
                "location": {"path": str(tmp_path / "Program.cs"), "line": 12},
            },
            {
                "id": "IDE0058",
                "severity": "Info",
                "message": "info",
                "location": {"path": str(tmp_path / "Program.cs"), "line": 13},
            },
        ]
    }

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        report_index = cmd.index("--report") + 1
        report_path = Path(cmd[report_index])
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return _FakeProcess(returncode=2)

    monkeypatch.setattr(
        "agent_review.collectors.roslyn.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "success"
    assert [f["severity"] for f in result.raw_findings] == ["HIGH", "HIGH", "LOW"]


@pytest.mark.asyncio
async def test_tc_ros_005_warning_non_security_maps_medium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.csproj").write_text("<Project />")
    (tmp_path / "Program.cs").write_text("class Program {}")

    payload = [
        {
            "id": "IDE0060",
            "severity": "Warning",
            "message": "unused",
            "location": {"path": str(tmp_path / "Program.cs"), "line": 20},
        }
    ]

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        report_index = cmd.index("--report") + 1
        report_path = Path(cmd[report_index])
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return _FakeProcess(returncode=2)

    monkeypatch.setattr(
        "agent_review.collectors.roslyn.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "success"
    assert result.raw_findings[0]["severity"] == "MEDIUM"


@pytest.mark.asyncio
async def test_tc_ros_006_cli_error_returns_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.csproj").write_text("<Project />")
    (tmp_path / "Program.cs").write_text("class Program {}")

    async def _fake_create_subprocess_exec(*_: str, **__: object) -> _FakeProcess:
        return _FakeProcess(returncode=1, stderr="dotnet failed")

    monkeypatch.setattr(
        "agent_review.collectors.roslyn.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "failure"
    assert "dotnet format exited with code 1" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_ros_007_uses_sln_when_csproj_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.sln").write_text("Microsoft Visual Studio Solution File")
    (tmp_path / "Program.cs").write_text("class Program {}")
    captured_cmd: list[str] = []

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        captured_cmd.extend(cmd)
        report_index = cmd.index("--report") + 1
        report_path = Path(cmd[report_index])
        report_path.write_text("[]", encoding="utf-8")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(
        "agent_review.collectors.roslyn.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "success"
    assert str(tmp_path / "App.sln") in captured_cmd


@pytest.mark.asyncio
async def test_tc_ros_008_strips_scan_dir_prefix_from_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.csproj").write_text("<Project />")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Program.cs").write_text("class Program {}")

    payload = {
        "diagnostics": [
            {
                "id": "CA3001",
                "severity": "Warning",
                "message": "security",
                "location": {"path": str(tmp_path / "src" / "Program.cs"), "line": 7},
            }
        ]
    }

    async def _fake_create_subprocess_exec(*cmd: str, **_: object) -> _FakeProcess:
        report_index = cmd.index("--report") + 1
        report_path = Path(cmd[report_index])
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return _FakeProcess(returncode=2)

    monkeypatch.setattr(
        "agent_review.collectors.roslyn.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"roslyn_mode": "cli"})
        collector = RoslynCollector(settings=settings, http_client=http_client)
        result = await collector.collect(_context(tmp_path))

    assert result.status == "success"
    assert result.raw_findings[0]["path"] == "src/Program.cs"
