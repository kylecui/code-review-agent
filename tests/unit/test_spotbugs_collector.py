from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.spotbugs import SpotBugsCollector
from agent_review.config import Settings


class _FakeProcess:
    returncode: int
    _stderr: bytes

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


def _spotbugs_context(tmp_path: Path, changed_files: list[str]) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=changed_files,
        local_path=str(tmp_path),
    )


def _settings(values: dict[str, object]) -> Settings:
    base: dict[str, object] = {
        "spotbugs_mode": "cli",
        "spotbugs_path": "spotbugs",
        "spotbugs_findsecbugs_plugin": "/opt/findsecbugs-plugin.jar",
        "spotbugs_effort": "max",
    }
    base.update(values)
    return Settings.model_validate(base)


@pytest.mark.asyncio
async def test_tc_sb_001_disabled_mode_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({"spotbugs_mode": "disabled"}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["src/Main.java"]))

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_sb_002_no_java_files_returns_skipped(tmp_path: Path) -> None:
    _ = (tmp_path / "README.md").write_text("# repo")

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["README.md"]))

    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_java_files"


@pytest.mark.asyncio
async def test_tc_sb_003_no_compiled_artifacts_returns_failure(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "Main.java").write_text("class Main {}")

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["src/Main.java"]))

    assert result.status == "failure"
    assert "compiled Java artifacts" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_sb_004_parses_sarif_and_strips_scan_dir_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "Main.java").write_text("class Main {}")
    (tmp_path / "target").mkdir()
    _ = (tmp_path / "target" / "Main.class").write_bytes(b"cafebabe")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = kwargs
        output_path = Path(cmd[cmd.index("-output") + 1])
        _ = output_path.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "tool": {"driver": {"name": "SpotBugs", "rules": [{"id": "SB1"}]}},
                            "results": [
                                {
                                    "ruleId": "SB1",
                                    "level": "warning",
                                    "message": {"text": "Potential issue"},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {
                                                    "uri": f"{tmp_path}/src/Main.java"
                                                },
                                                "region": {"startLine": 7},
                                            }
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            )
        )
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["src/Main.java"]))

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    finding = result.raw_findings[0]
    assert finding["rule_id"] == "SB1"
    assert finding["path"] == "src/Main.java"
    assert finding["severity"] == "WARNING"


@pytest.mark.asyncio
async def test_tc_sb_005_cli_nonzero_returns_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "Main.java").write_text("class Main {}")
    _ = (tmp_path / "Main.class").write_bytes(b"x")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = (cmd, kwargs)
        return _FakeProcess(returncode=2, stderr=b"spotbugs error")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["Main.java"]))

    assert result.status == "failure"
    assert "exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_sb_006_settings_passthrough_to_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "Main.java").write_text("class Main {}")
    _ = (tmp_path / "Main.class").write_bytes(b"x")

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        captured["cmd"] = list(cmd)
        output_path = Path(cmd[cmd.index("-output") + 1])
        _ = output_path.write_text('{"runs": []}')
        _ = kwargs
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(
            _settings(
                {
                    "spotbugs_path": "/custom/spotbugs",
                    "spotbugs_findsecbugs_plugin": "/plugins/findsecbugs.jar",
                    "spotbugs_effort": "min",
                }
            ),
            http_client,
        )
        result = await collector.collect(_spotbugs_context(tmp_path, ["Main.java"]))

    cmd = cast(list[str], captured["cmd"])
    assert result.status == "success"
    assert cmd[0] == "/custom/spotbugs"
    assert "-effort:min" in cmd
    assert "-pluginList" in cmd
    assert "/plugins/findsecbugs.jar" in cmd


@pytest.mark.asyncio
async def test_tc_sb_007_top_level_exception_returns_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "Main.java").write_text("class Main {}")
    _ = (tmp_path / "Main.class").write_bytes(b"x")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = (cmd, kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = SpotBugsCollector(_settings({}), http_client)
        result = await collector.collect(_spotbugs_context(tmp_path, ["Main.java"]))

    assert result.status == "failure"
    assert "boom" in (result.error or "")
