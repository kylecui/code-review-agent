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


def test_normalize_semgrep_mapping_and_fingerprint_stability() -> None:
    normalizer = FindingsNormalizer()
    result = _result(
        "semgrep",
        [
            {
                "rule_id": "python.lang.security.audit.hardcoded-password",
                "path": "src/app.py",
                "line": 42,
                "severity": "ERROR",
                "message": "Hardcoded password detected",
            }
        ],
    )

    first = normalizer.normalize([result])
    second = normalizer.normalize([result])

    assert len(first) == 1
    finding = first[0]
    assert (
        finding.finding_id == "semgrep:python.lang.security.audit.hardcoded-password:src/app.py:42"
    )
    assert finding.severity.value == "high"
    assert finding.confidence.value == "high"
    assert finding.blocking is True
    assert finding.fingerprint == second[0].fingerprint


def test_normalize_sonar_mapping() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "sonar",
                [
                    {
                        "key": "AXX-1",
                        "rule": "python:S1481",
                        "severity": "MAJOR",
                        "type": "BUG",
                        "message": "Unused local variable",
                        "component": "src/module.py",
                        "line": 12,
                    }
                ],
            )
        ]
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.finding_id == "sonar:AXX-1"
    assert finding.category == "quality.bug"
    assert finding.severity.value == "medium"
    assert finding.confidence.value == "medium"


def test_normalize_github_ci_mapping_uses_annotation_level() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "github_ci",
                [
                    {
                        "check_name": "ruff",
                        "status": "failure",
                        "path": "src/a.py",
                        "start_line": 5,
                        "end_line": 5,
                        "annotation_level": "notice",
                        "message": "Style issue",
                        "title": "RUF100",
                    }
                ],
            )
        ]
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity.value == "low"
    assert finding.confidence.value == "low"
    assert finding.line_end == 5


def test_normalize_secrets_always_critical() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "secrets",
                [
                    {
                        "number": 7,
                        "state": "open",
                        "secret_type": "AWS Access Key",
                        "html_url": "https://example.test/alert/7",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
            )
        ]
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.finding_id == "secrets:7"
    assert finding.category == "security.secret-detection"
    assert finding.severity.value == "critical"
    assert finding.blocking is True


def test_normalize_skips_non_success_and_errored_results() -> None:
    normalizer = FindingsNormalizer()
    findings = normalizer.normalize(
        [
            _result(
                "semgrep", [{"rule_id": "x", "path": "a", "line": 1, "severity": "INFO"}], "failure"
            ),
            _result("sonar", [{"key": "x"}], "success", error="API down"),
            _result("unknown", [{"x": 1}], "success"),
        ]
    )
    assert findings == []
