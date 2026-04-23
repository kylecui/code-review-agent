from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_review.collectors.base import CollectorContext
from agent_review.collectors.codeql import CodeQLCollector
from agent_review.config import Settings


_DEFAULT_LOCAL_PATH = object()


class _FakeProc:
    def __init__(self, returncode: int = 0, stderr: bytes = b"", sleep_seconds: float = 0.0):
        self.returncode: int = returncode
        self._stderr: bytes = stderr
        self._sleep_seconds: float = sleep_seconds
        self.killed: bool = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._sleep_seconds > 0:
            await asyncio.sleep(self._sleep_seconds)
        return b"", self._stderr

    def kill(self) -> None:
        self.killed = True


def _make_settings(values: dict[str, object]) -> Settings:
    return Settings.model_validate(
        {
            "codeql_mode": "cli",
            "codeql_path": "codeql",
            "codeql_timeout": 2,
            **values,
        }
    )


def _make_context(
    tmp_path: Path, local_path: str | None | object = _DEFAULT_LOCAL_PATH
) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        head_sha="a" * 40,
        changed_files=[],
        local_path=(str(tmp_path) if local_path is _DEFAULT_LOCAL_PATH else local_path),
    )


def _sarif_payload(
    path: str = "src/app.py", rule_id: str = "py/sql-injection"
) -> dict[str, object]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": rule_id,
                                "properties": {
                                    "category": "security",
                                    "precision": "high",
                                    "cwe": ["CWE-89"],
                                },
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": rule_id,
                        "level": "warning",
                        "message": {"text": "Potential taint flow"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": path},
                                    "region": {
                                        "startLine": 7,
                                        "endLine": 9,
                                        "snippet": {"text": "cursor.execute(query)"},
                                    },
                                }
                            }
                        ],
                        "partialFingerprints": {"primaryLocationLineHash": "fp-1"},
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_tc_cql_001_disabled_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(
            settings=_make_settings({"codeql_mode": "disabled"}),
            http_client=http_client,
        )
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_tc_cql_002_no_local_path_returns_skipped(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path, local_path=None))

    assert result.status == "skipped"
    assert "local_path" in str(result.metadata.get("note", ""))


@pytest.mark.asyncio
async def test_tc_cql_003_success_runs_create_and_analyze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_cmds: list[list[str]] = []

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        captured_cmds.append(list(cmd))
        if list(cmd)[1:3] == ["database", "analyze"]:
            output_arg = next(arg for arg in cmd if arg.startswith("--output="))
            output_path = Path(output_arg.split("=", 1)[1])
            _ = output_path.write_text(
                json.dumps(_sarif_payload(path=str(tmp_path / "src/app.py"))),
                encoding="utf-8",
            )
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "success"
    assert len(captured_cmds) == 2
    assert captured_cmds[0][1:3] == ["database", "create"]
    assert captured_cmds[1][1:3] == ["database", "analyze"]
    assert "--format=sarif-latest" in captured_cmds[1]


@pytest.mark.asyncio
async def test_tc_cql_004_analyze_timeout_returns_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    timed_procs: list[_FakeProc] = []

    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        if list(cmd)[1:3] == ["database", "analyze"]:
            timed_proc = _FakeProc(returncode=0, sleep_seconds=1.1)
            timed_procs.append(timed_proc)
            return timed_proc
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(
            settings=_make_settings({"codeql_timeout": 1}),
            http_client=http_client,
        )
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "timeout"
    assert len(timed_procs) == 1
    assert timed_procs[0].killed is True


@pytest.mark.asyncio
async def test_tc_cql_005_process_error_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        if list(cmd)[1:3] == ["database", "create"]:
            return _FakeProc(returncode=2, stderr=b"db create failed")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "failure"
    assert "database create exited with code 2" in (result.error or "")


@pytest.mark.asyncio
async def test_tc_cql_006_empty_sarif_results_returns_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        if list(cmd)[1:3] == ["database", "analyze"]:
            output_arg = next(arg for arg in cmd if arg.startswith("--output="))
            output_path = Path(output_arg.split("=", 1)[1])
            _ = output_path.write_text(
                json.dumps({"version": "2.1.0", "runs": []}),
                encoding="utf-8",
            )
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "success"
    assert result.raw_findings == []


@pytest.mark.asyncio
async def test_tc_cql_007_sarif_parse_to_required_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = kwargs
        if list(cmd)[1:3] == ["database", "analyze"]:
            output_arg = next(arg for arg in cmd if arg.startswith("--output="))
            output_path = Path(output_arg.split("=", 1)[1])
            _ = output_path.write_text(json.dumps(_sarif_payload()), encoding="utf-8")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "success"
    finding = result.raw_findings[0]
    assert set(finding.keys()) == {
        "rule_id",
        "path",
        "line",
        "end_line",
        "severity",
        "message",
        "snippet",
        "cwe",
        "precision",
        "category",
    }


@pytest.mark.asyncio
async def test_tc_cql_008_multiple_findings_from_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        return _FakeProc(returncode=0)

    def _fake_parse_file(_self: object, _path: Path) -> list[dict[str, object]]:
        return [
            {
                "rule_id": "r1",
                "path": "a.py",
                "line": 1,
                "end_line": 1,
                "severity": "WARNING",
                "message": "m1",
                "snippet": "x",
                "cwe": ["CWE-79"],
                "precision": "high",
                "category": "security",
            },
            {
                "rule_id": "r2",
                "path": "b.py",
                "line": 2,
                "end_line": 3,
                "severity": "ERROR",
                "message": "m2",
                "snippet": "y",
                "cwe": ["CWE-89"],
                "precision": "medium",
                "category": "security",
            },
        ]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("agent_review.collectors.codeql.SarifAdapter.parse_file", _fake_parse_file)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "success"
    assert len(result.raw_findings) == 2
    assert result.raw_findings[0]["rule_id"] == "r1"
    assert result.raw_findings[1]["rule_id"] == "r2"


@pytest.mark.asyncio
async def test_tc_cql_009_subprocess_spawn_exception_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        _ = cmd
        _ = kwargs
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async with httpx.AsyncClient() as http_client:
        collector = CodeQLCollector(settings=_make_settings({}), http_client=http_client)
        result = await collector.collect(_make_context(tmp_path))

    assert result.status == "failure"
    assert "spawn failed" in (result.error or "")
