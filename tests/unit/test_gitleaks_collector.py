from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.gitleaks import GitleaksCollector
from agent_review.config import Settings


def _sarif_payload(path: str = "repo/main.go", level: str = "warning") -> dict[str, object]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "gitleaks",
                        "rules": [
                            {
                                "id": "secret.rule",
                                "properties": {
                                    "category": "security",
                                    "precision": "high",
                                    "cwe": ["CWE-798"],
                                },
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": "secret.rule",
                        "level": level,
                        "message": {"text": "Hardcoded secret"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": path},
                                    "region": {"startLine": 3, "endLine": 3},
                                }
                            }
                        ],
                        "partialFingerprints": {"primaryLocationLineHash": "fp-1"},
                    }
                ],
            }
        ],
    }


class _FakeProc:
    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode: int = returncode
        self._stderr: bytes = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


@pytest.mark.asyncio
async def test_tc_gl_001_disabled_mode_returns_skipped() -> None:
    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "disabled"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=[])

        result = await collector.collect(context)

    assert result.status == "skipped"
    assert result.metadata["mode"] == "disabled"


@pytest.mark.asyncio
async def test_tc_gl_002_sarif_parse_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        report_index = list(cmd).index("--report-path") + 1
        _ = Path(cmd[report_index]).write_text(json.dumps(_sarif_payload()), encoding="utf-8")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "cli"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            head_sha="a" * 40,
            changed_files=[],
            local_path=str(tmp_path),
        )

        result = await collector.collect(context)

    assert result.status == "success"
    assert len(result.raw_findings) == 1
    assert result.raw_findings[0]["rule_id"] == "secret.rule"


@pytest.mark.asyncio
async def test_tc_gl_003_severity_mapping_from_sarif(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        report_index = list(cmd).index("--report-path") + 1
        _ = Path(cmd[report_index]).write_text(
            json.dumps(_sarif_payload(level="error")),
            encoding="utf-8",
        )
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "cli"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            head_sha="a" * 40,
            changed_files=[],
            local_path=str(tmp_path),
        )
        result = await collector.collect(context)

    assert result.status == "success"
    assert result.raw_findings[0]["severity"] == "ERROR"


@pytest.mark.asyncio
async def test_tc_gl_004_cli_error_returns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(returncode=2, stderr=b"boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "cli"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=[])
        result = await collector.collect(context)

    assert result.status == "failure"
    assert "exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_gl_005_custom_config_path_used(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cmd: list[str] = []

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        captured_cmd.extend(list(cmd))
        report_index = list(cmd).index("--report-path") + 1
        _ = Path(cmd[report_index]).write_text(json.dumps(_sarif_payload()), encoding="utf-8")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate(
            {
                "gitleaks_mode": "cli",
                "gitleaks_config_path": "/tmp/gitleaks.toml",
            }
        )
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=[])
        result = await collector.collect(context)

    assert result.status == "success"
    assert "--config" in captured_cmd
    assert "/tmp/gitleaks.toml" in captured_cmd


@pytest.mark.asyncio
async def test_tc_gl_006_strip_scan_dir_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    absolute_path = str(tmp_path / "nested" / "secret.go")

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        report_index = list(cmd).index("--report-path") + 1
        _ = Path(cmd[report_index]).write_text(
            json.dumps(_sarif_payload(path=absolute_path)), encoding="utf-8"
        )
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "cli"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(
            repo="o/r",
            head_sha="a" * 40,
            changed_files=[],
            local_path=str(tmp_path),
        )
        result = await collector.collect(context)

    assert result.status == "success"
    assert result.raw_findings[0]["path"] == "nested/secret.go"


@pytest.mark.asyncio
async def test_tc_gl_007_subprocess_exception_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        settings = Settings.model_validate({"gitleaks_mode": "cli"})
        collector = GitleaksCollector(settings=settings, http_client=http_client)
        context = CollectorContext(repo="o/r", head_sha="a" * 40, changed_files=[])
        result = await collector.collect(context)

    assert result.status == "failure"
    assert "spawn failed" in (result.error or "")
