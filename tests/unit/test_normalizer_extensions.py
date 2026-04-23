from __future__ import annotations

from typing import TYPE_CHECKING, cast

from agent_review.collectors.base import CollectorResult
from agent_review.normalize.normalizer import FindingsNormalizer

if TYPE_CHECKING:
    from agent_review.collectors.base import CollectorStatus


def _result(
    collector_name: str,
    raw_findings: list[dict[str, object]],
    status: str = "success",
    error: str | None = None,
) -> CollectorResult:
    return CollectorResult(
        collector_name=collector_name,
        status=cast("CollectorStatus", status),
        raw_findings=raw_findings,
        duration_ms=10,
        error=error,
    )


def test_normalize_gitleaks_maps_to_secret_detection() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "gitleaks",
                [
                    {
                        "rule_id": "aws-access-key",
                        "path": "config/secrets.py",
                        "line": 5,
                        "severity": "ERROR",
                        "message": "AWS Access Key detected",
                        "snippet": 'AWS_KEY = "AKIA..."',
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "security.secret-detection"
    assert f.severity.value == "high"
    assert f.confidence.value == "high"
    assert f.blocking is True
    assert f.finding_id == "gitleaks:aws-access-key:config/secrets.py:5"


def test_normalize_spotbugs_maps_sarif_severity() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "spotbugs",
                [
                    {
                        "rule_id": "SQL_INJECTION",
                        "path": "src/Main.java",
                        "line": 42,
                        "severity": "ERROR",
                        "message": "SQL injection vulnerability",
                        "category": "security",
                        "cwe": ["CWE-89"],
                        "precision": "high",
                        "snippet": "",
                        "tool_name": "SpotBugs",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "security.sast"
    assert f.severity.value == "high"
    assert f.confidence.value == "high"
    assert f.rule_id == "SQL_INJECTION"


def test_normalize_golangci_lint_maps_category() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "golangci_lint",
                [
                    {
                        "rule_id": "G101",
                        "path": "cmd/server.go",
                        "line": 15,
                        "severity": "WARNING",
                        "message": "Potential hardcoded credentials",
                        "category": "security",
                        "cwe": [],
                        "precision": "medium",
                        "snippet": "",
                        "tool_name": "gosec",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "security.sast"
    assert f.severity.value == "medium"
    assert f.finding_id == "golangci_lint:G101:cmd/server.go:15"


def test_normalize_cppcheck_quality_category() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "cppcheck",
                [
                    {
                        "rule_id": "nullPointer",
                        "path": "src/main.c",
                        "line": 20,
                        "severity": "ERROR",
                        "message": "Null pointer dereference",
                        "category": "unknown",
                        "cwe": [],
                        "precision": "unknown",
                        "snippet": "",
                        "tool_name": "Cppcheck",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "quality.static-analysis"
    assert f.severity.value == "high"
    assert f.title == "Cppcheck: nullPointer"


def test_normalize_eslint_security_rule_promotes_to_high() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "eslint_security",
                [
                    {
                        "rule_id": "security/detect-eval-with-expression",
                        "path": "src/app.js",
                        "line": 10,
                        "severity": 2,
                        "message": "eval with expression",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "security.sast"
    assert f.severity.value == "high"
    assert f.blocking is True


def test_normalize_eslint_non_security_error_maps_to_medium() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "eslint_security",
                [
                    {
                        "rule_id": "no-unused-vars",
                        "path": "src/util.ts",
                        "line": 3,
                        "severity": 2,
                        "message": "Variable is defined but never used",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "quality.static-analysis"
    assert f.severity.value == "medium"


def test_normalize_roslyn_maps_via_sarif() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "roslyn",
                [
                    {
                        "rule_id": "CA2100",
                        "path": "Controllers/HomeController.cs",
                        "line": 30,
                        "severity": "WARNING",
                        "message": "Review SQL queries for security vulnerabilities",
                        "category": "security",
                        "cwe": ["CWE-89"],
                        "precision": "medium",
                        "snippet": "",
                        "tool_name": "Roslyn",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "security.sast"
    assert f.severity.value == "medium"
    assert f.rule_id == "CA2100"


def test_normalize_luacheck_error_code_high_severity() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "luacheck",
                [
                    {
                        "rule_id": "E011",
                        "path": "src/main.lua",
                        "line": 5,
                        "severity": "ERROR",
                        "message": "expected expression near 'end'",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "quality.syntax-error"
    assert f.severity.value == "high"
    assert f.blocking is True


def test_normalize_luacheck_warning_code_low_severity() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "luacheck",
                [
                    {
                        "rule_id": "W111",
                        "path": "lib/utils.lua",
                        "line": 12,
                        "severity": "WARNING",
                        "message": "setting non-standard global variable foo",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "quality.static-analysis"
    assert f.severity.value == "low"


def test_normalize_unknown_collector_returns_empty() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [_result("nonexistent_tool", [{"rule_id": "x", "path": "a", "line": 1}])]
    )
    assert findings == []


def test_normalize_mixed_old_and_new_collectors() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "semgrep",
                [
                    {
                        "rule_id": "python.security.xss",
                        "path": "app.py",
                        "line": 1,
                        "severity": "ERROR",
                        "message": "XSS",
                    }
                ],
            ),
            _result(
                "gitleaks",
                [
                    {
                        "rule_id": "generic-api-key",
                        "path": "env.py",
                        "line": 2,
                        "severity": "ERROR",
                        "message": "API key",
                    }
                ],
            ),
            _result(
                "cppcheck",
                [
                    {
                        "rule_id": "memleak",
                        "path": "main.c",
                        "line": 3,
                        "severity": "WARNING",
                        "message": "Memory leak",
                        "category": "unknown",
                        "cwe": [],
                        "precision": "unknown",
                        "snippet": "",
                        "tool_name": "Cppcheck",
                    }
                ],
            ),
            _result(
                "luacheck",
                [
                    {
                        "rule_id": "W211",
                        "path": "init.lua",
                        "line": 4,
                        "severity": "WARNING",
                        "message": "unused var",
                    }
                ],
            ),
        ]
    )
    assert len(findings) == 4
    tool_sources = {f.source_tools[0] for f in findings}
    assert tool_sources == {"semgrep", "gitleaks", "cppcheck", "luacheck"}


def test_normalize_codeql_uses_sarif_based_with_security_default() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "codeql",
                [
                    {
                        "rule_id": "py/sql-injection",
                        "path": "app/db.py",
                        "line": 42,
                        "end_line": 42,
                        "severity": "ERROR",
                        "message": "Potential SQL injection",
                        "snippet": "cursor.execute(query)",
                        "cwe": ["CWE-89"],
                        "precision": "high",
                        "category": "security",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.source_tools == ["codeql"]
    assert f.category == "security.sast"
    assert f.title == "CodeQL: py/sql-injection"
    assert f.file_path == "app/db.py"
    assert f.line_start == 42
    assert "CWE-89" in " ".join(f.evidence)


def test_normalize_codeql_unknown_category_defaults_to_security_sast() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "codeql",
                [
                    {
                        "rule_id": "py/unused-import",
                        "path": "lib/utils.py",
                        "line": 1,
                        "severity": "WARNING",
                        "message": "Unused import",
                        "category": "",
                    }
                ],
            )
        ]
    )
    assert len(findings) == 1
    assert findings[0].category == "security.sast"
