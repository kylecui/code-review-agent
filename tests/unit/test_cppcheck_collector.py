from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.cppcheck import CppcheckCollector
from agent_review.config import Settings


class _FakeProcess:
    returncode: int
    _stderr: bytes

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


def _cpp_context(tmp_path: Path, changed_files: list[str]) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=changed_files,
        local_path=str(tmp_path),
    )


def _settings(values: dict[str, object]) -> Settings:
    base: dict[str, object] = {
        "cppcheck_mode": "cli",
        "cppcheck_enable": "all",
        "cppcheck_suppressions": ["missingIncludeSystem"],
    }
    base.update(values)
    return Settings.model_validate(base)


@pytest.mark.asyncio
async def test_tc_cpp_001_disabled_mode_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({"cppcheck_mode": "disabled"}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["src/main.cpp"]))

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_cpp_002_no_cpp_files_returns_skipped(tmp_path: Path) -> None:
    _ = (tmp_path / "README.md").write_text("# repo")

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["README.md"]))

    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_cpp_files"


@pytest.mark.asyncio
async def test_tc_cpp_003_parses_sarif_and_severity_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "main.cpp").write_text("int main() { return 0; }")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = kwargs
        output_flag = next(part for part in cmd if part.startswith("--output-file="))
        output_path = Path(output_flag.split("=", 1)[1])
        _ = output_path.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "tool": {"driver": {"name": "Cppcheck", "rules": [{"id": "cpp-1"}]}},
                            "results": [
                                {
                                    "ruleId": "cpp-1",
                                    "level": "error",
                                    "message": {"text": "Buffer issue"},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {
                                                    "uri": f"{tmp_path}/src/main.cpp"
                                                },
                                                "region": {"startLine": 3},
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
        return _FakeProcess(returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["src/main.cpp"]))

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    finding = result.raw_findings[0]
    assert finding["rule_id"] == "cpp-1"
    assert finding["path"] == "src/main.cpp"
    assert finding["severity"] == "ERROR"


@pytest.mark.asyncio
async def test_tc_cpp_004_cli_error_returns_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "main.c").write_text("int main() { return 0; }")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = (cmd, kwargs)
        return _FakeProcess(returncode=2, stderr=b"broken")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["main.c"]))

    assert result.status == "failure"
    assert "exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_cpp_005_cppcheck_not_installed_returns_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "main.cc").write_text("int main() { return 0; }")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = (cmd, kwargs)
        raise FileNotFoundError("cppcheck")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["main.cc"]))

    assert result.status == "failure"
    assert "not installed" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_cpp_006_settings_passthrough_to_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "main.cxx").write_text("int main() { return 0; }")

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        captured["cmd"] = list(cmd)
        output_flag = next(part for part in cmd if part.startswith("--output-file="))
        _ = Path(output_flag.split("=", 1)[1]).write_text('{"runs": []}')
        _ = kwargs
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(
            _settings({"cppcheck_enable": "warning", "cppcheck_suppressions": ["a", "b"]}),
            http_client,
        )
        result = await collector.collect(_cpp_context(tmp_path, ["main.cxx"]))

    cmd = cast("list[str]", captured["cmd"])
    assert result.status == "success"
    assert "--enable=warning" in cmd
    assert "--suppress=a" in cmd
    assert "--suppress=b" in cmd


@pytest.mark.asyncio
async def test_tc_cpp_007_top_level_exception_returns_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "main.h").write_text("int x;")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        _ = (cmd, kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CppcheckCollector(_settings({}), http_client)
        result = await collector.collect(_cpp_context(tmp_path, ["main.h"]))

    assert result.status == "failure"
    assert "boom" in (result.error or "")
