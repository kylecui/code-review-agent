from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.golangci_lint import GolangciLintCollector
from agent_review.config import Settings


def _sarif_payload(path: str = "repo/pkg/main.go", level: str = "warning") -> dict[str, object]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "golangci-lint",
                        "rules": [
                            {
                                "id": "go.rule",
                                "properties": {
                                    "category": "style",
                                    "precision": "medium",
                                },
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": "go.rule",
                        "level": level,
                        "message": {"text": "lint issue"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": path},
                                    "region": {"startLine": 7, "endLine": 7},
                                }
                            }
                        ],
                        "partialFingerprints": {"primaryLocationLineHash": "go-fp"},
                    }
                ],
            }
        ],
    }


class _FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout: bytes = stdout
        self._stderr: bytes = stderr
        self.returncode: int = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_tc_gcl_001_disabled_mode_returns_skipped() -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "disabled"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=["main.go"])

        result = await collector.collect(context)

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_gcl_002_no_go_files_returns_skipped(tmp_path: Path) -> None:
    _ = (tmp_path / "README.md").write_text("docs", encoding="utf-8")
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "cli"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            head_sha="a" * 40,
            changed_files=["README.md"],
            local_path=str(tmp_path),
        )

        result = await collector.collect(context)

    assert result.status == "skipped"
    assert result.metadata["reason"] == "no_go_files"


@pytest.mark.asyncio
async def test_tc_gcl_003_sarif_parse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(stdout=json.dumps(_sarif_payload()).encode("utf-8"), returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "cli"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=["pkg/main.go"])

        result = await collector.collect(context)

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["rule_id"] == "go.rule"


@pytest.mark.asyncio
async def test_tc_gcl_004_severity_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(
            stdout=json.dumps(_sarif_payload(level="error")).encode("utf-8"), returncode=1
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "cli"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=["pkg/main.go"])
        result = await collector.collect(context)

    assert result.status == "success"
    assert result.raw_findings[0]["severity"] == "ERROR"


@pytest.mark.asyncio
async def test_tc_gcl_005_cli_error_returns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(stderr=b"fatal", returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "cli"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=["pkg/main.go"])
        result = await collector.collect(context)

    assert result.status == "failure"
    assert "exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_gcl_006_custom_config_path_used(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cmd: list[str] = []

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        captured_cmd.extend(list(cmd))
        return _FakeProc(stdout=json.dumps(_sarif_payload()).encode("utf-8"), returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate(
            {
                "golangci_lint_mode": "cli",
                "golangci_lint_config_path": "/tmp/.golangci.yml",
            }
        )
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=["pkg/main.go"])
        result = await collector.collect(context)

    assert result.status == "success"
    assert "--config" in captured_cmd
    assert "/tmp/.golangci.yml" in captured_cmd


@pytest.mark.asyncio
async def test_tc_gcl_007_strip_scan_dir_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pkg").mkdir()
    _ = (tmp_path / "pkg" / "main.go").write_text("package main", encoding="utf-8")
    absolute_path = str(tmp_path / "pkg" / "main.go")

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(
            stdout=json.dumps(_sarif_payload(path=absolute_path)).encode("utf-8"), returncode=0
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"golangci_lint_mode": "cli"})
        collector = GolangciLintCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            head_sha="a" * 40,
            changed_files=[],
            local_path=str(tmp_path),
        )
        result = await collector.collect(context)

    assert result.status == "success"
    assert result.raw_findings[0]["path"] == "pkg/main.go"
