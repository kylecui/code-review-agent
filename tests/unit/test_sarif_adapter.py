from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from types import ModuleType


def _load_sarif_adapter_module() -> ModuleType:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_root_str = str(src_root)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)
    return import_module("agent_review.normalize.sarif_adapter")


sarif_adapter_module = _load_sarif_adapter_module()
SarifAdapter = cast("type[Any]", sarif_adapter_module.SarifAdapter)


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "sarif"


def _load_fixture(name: str) -> dict[str, object]:
    fixture_path = _fixtures_dir() / name
    with fixture_path.open("r", encoding="utf-8") as file:
        return cast("dict[str, object]", json.load(file))


def test_tc_sarif_001_parse_json_valid_three_results() -> None:
    """TC-SARIF-001: 1 run with 3 results returns 3 findings."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "generic", "rules": [{"id": "R1"}]}},
                "results": [
                    {
                        "ruleId": "R1",
                        "level": "warning",
                        "message": {"text": "f1"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "a.py"},
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    },
                    {
                        "ruleId": "R1",
                        "level": "note",
                        "message": {"text": "f2"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "b.py"},
                                    "region": {"startLine": 2},
                                }
                            }
                        ],
                    },
                    {
                        "ruleId": "R1",
                        "level": "error",
                        "message": {"text": "f3"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "c.py"},
                                    "region": {"startLine": 3},
                                }
                            }
                        ],
                    },
                ],
            }
        ],
    }

    findings = adapter.parse_json(sarif_data)

    assert len(findings) == 3


def test_tc_sarif_002_parse_json_empty_results_returns_empty() -> None:
    """TC-SARIF-002: empty results returns empty list."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "x"}}, "results": []}],
    }

    assert adapter.parse_json(sarif_data) == []


def test_tc_sarif_003_parse_json_missing_locations_defaults_unknown() -> None:
    """TC-SARIF-003: missing locations yields path unknown and line 0."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "x", "rules": [{"id": "R1"}]}},
                "results": [{"ruleId": "R1", "message": {"text": "m"}}],
            }
        ],
    }

    findings = adapter.parse_json(sarif_data)

    assert len(findings) == 1
    assert findings[0]["path"] == "unknown"
    assert findings[0]["line"] == 0


def test_tc_sarif_004_resolve_rule_by_rule_index_driver_rules() -> None:
    """TC-SARIF-004: rule metadata resolved by tool.driver.rules + ruleIndex."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "x",
                        "rules": [
                            {
                                "id": "R1",
                                "properties": {
                                    "category": "security.sast",
                                    "precision": "high",
                                },
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleIndex": 0,
                        "message": {"text": "m"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "a.py"},
                                    "region": {"startLine": 5},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["category"] == "security.sast"
    assert findings[0]["precision"] == "high"


def test_tc_sarif_005_resolve_rule_from_tool_extensions_codeql_pattern() -> None:
    """TC-SARIF-005: resolve metadata from tool.extensions rules."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("codeql_sample.json")

    findings = adapter.parse_json(sarif_data)

    assert len(findings) == 1
    assert findings[0]["rule_id"] == "py/sql-injection"
    assert findings[0]["category"] == "security.sast"


def test_tc_sarif_006_extract_partial_fingerprints_when_present() -> None:
    """TC-SARIF-006: partialFingerprints value is used as fingerprint."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("gitleaks_sample.json")

    findings = adapter.parse_json(sarif_data)

    assert len(findings) == 1
    assert findings[0]["fingerprint"] == "gitleaks-fp-123"


def test_tc_sarif_007_extract_cwe_from_properties_cwe() -> None:
    """TC-SARIF-007: CWE extracted from rule.properties.cwe."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("gitleaks_sample.json")

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["cwe"] == ["CWE-798"]


def test_tc_sarif_008_map_error_to_error() -> None:
    """TC-SARIF-008: level error maps to ERROR."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("gitleaks_sample.json")

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["severity"] == "ERROR"


def test_tc_sarif_009_map_warning_to_warning() -> None:
    """TC-SARIF-009: level warning maps to WARNING."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("minimal_valid.json")

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["severity"] == "WARNING"


def test_tc_sarif_010_map_note_to_info() -> None:
    """TC-SARIF-010: level note maps to INFO."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("minimal_valid.json")
    runs = cast("list[dict[str, object]]", sarif_data["runs"])
    first_run = runs[0]
    results = cast("list[dict[str, object]]", first_run["results"])
    results[0]["level"] = "note"

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["severity"] == "INFO"


def test_tc_sarif_011_map_none_to_info() -> None:
    """TC-SARIF-011: level none maps to INFO."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("minimal_valid.json")
    runs = cast("list[dict[str, object]]", sarif_data["runs"])
    first_run = runs[0]
    results = cast("list[dict[str, object]]", first_run["results"])
    results[0]["level"] = "none"

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["severity"] == "INFO"


def test_tc_sarif_012_extract_snippet_from_region_snippet_text() -> None:
    """TC-SARIF-012: snippet extracted from region.snippet.text."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("minimal_valid.json")

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["snippet"] == "print(user_input)"


def test_tc_sarif_013_malformed_sarif_returns_empty_and_logs_warning(monkeypatch) -> None:
    """TC-SARIF-013: malformed SARIF is handled gracefully."""
    adapter = SarifAdapter()
    warning_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_warning(*args: object, **kwargs: object) -> None:
        warning_calls.append((args, cast("dict[str, object]", kwargs)))

    monkeypatch.setattr(sarif_adapter_module.logger, "warning", fake_warning)

    findings = adapter.parse_json(cast("dict[str, object]", {"runs": "not-a-list"}))

    assert findings == []
    assert warning_calls
    assert warning_calls[0][0][0] == "invalid_sarif_runs"


def test_tc_sarif_014_missing_runs_key_returns_empty() -> None:
    """TC-SARIF-014: missing runs key returns empty list."""
    adapter = SarifAdapter()

    findings = adapter.parse_json({"$schema": "https://json.schemastore.org/sarif-2.1.0.json"})

    assert findings == []


def test_tc_sarif_015_parse_file_reads_disk_and_delegates(monkeypatch, tmp_path: Path) -> None:
    """TC-SARIF-015: parse_file loads JSON then delegates to parse_json."""
    adapter = SarifAdapter()
    file_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [],
    }
    sarif_file = tmp_path / "input.sarif"
    sarif_file.write_text(json.dumps(file_data), encoding="utf-8")

    seen: list[dict[str, object]] = []

    def fake_parse_json(payload: dict[str, object]) -> list[dict[str, object]]:
        seen.append(payload)
        return [{"rule_id": "X"}]

    monkeypatch.setattr(adapter, "parse_json", fake_parse_json)

    findings = adapter.parse_file(sarif_file)

    assert findings == [{"rule_id": "X"}]
    assert seen == [file_data]


def test_tc_sarif_016_parse_json_multiple_runs_aggregates_results() -> None:
    """TC-SARIF-016: multiple runs are aggregated."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "tool-a", "rules": [{"id": "A"}]}},
                "results": [
                    {
                        "ruleId": "A",
                        "message": {"text": "a"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "a.py"},
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    }
                ],
            },
            {
                "tool": {"driver": {"name": "tool-b", "rules": [{"id": "B"}]}},
                "results": [
                    {
                        "ruleId": "B",
                        "message": {"text": "b"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "b.py"},
                                    "region": {"startLine": 2},
                                }
                            }
                        ],
                    }
                ],
            },
        ],
    }

    findings = adapter.parse_json(sarif_data)

    assert len(findings) == 2
    assert {finding["rule_id"] for finding in findings} == {"A", "B"}


def test_tc_sarif_017_extract_tool_name_from_driver_name() -> None:
    """TC-SARIF-017: tool_name extracted from run.tool.driver.name."""
    adapter = SarifAdapter()
    sarif_data = _load_fixture("gitleaks_sample.json")

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["tool_name"] == "gitleaks"


def test_tc_sarif_018_uri_base_id_resolves_relative_paths() -> None:
    """TC-SARIF-018: uriBaseId relative path is resolved."""
    adapter = SarifAdapter()
    sarif_data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "x", "rules": [{"id": "R1"}]}},
                "originalUriBaseIds": {
                    "SRCROOT": {"uri": "file:///workspace/repo/"},
                },
                "results": [
                    {
                        "ruleId": "R1",
                        "message": {"text": "m"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": "src/module.py",
                                        "uriBaseId": "SRCROOT",
                                    },
                                    "region": {"startLine": 7},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }

    findings = adapter.parse_json(sarif_data)

    assert findings[0]["path"] == "/workspace/repo/src/module.py"
