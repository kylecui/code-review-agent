from __future__ import annotations

from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.normalize.dedup import FindingsDeduplicator
from agent_review.schemas.finding import FindingCreate


def _finding(
    finding_id: str,
    fingerprint: str,
    severity: FindingSeverity,
    source_tool: str,
    evidence: list[str],
) -> FindingCreate:
    return FindingCreate(
        finding_id=finding_id,
        category="quality.issue",
        severity=severity,
        confidence=FindingConfidence.MEDIUM,
        blocking=severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH},
        file_path="src/a.py",
        line_start=1,
        source_tools=[source_tool],
        title=finding_id,
        evidence=evidence,
        impact="impact",
        fix_recommendation="fix",
        fingerprint=fingerprint,
    )


def test_deduplicate_merges_by_fingerprint_and_keeps_highest_severity() -> None:
    dedup = FindingsDeduplicator()
    findings = [
        _finding("a", "fp-1", FindingSeverity.MEDIUM, "sonar", ["e1"]),
        _finding("b", "fp-1", FindingSeverity.HIGH, "semgrep", ["e2"]),
        _finding("c", "fp-2", FindingSeverity.LOW, "github_ci", ["e3"]),
    ]

    out = dedup.deduplicate(findings)

    assert len(out) == 2
    assert out[0].severity == FindingSeverity.HIGH
    assert sorted(out[0].source_tools) == ["semgrep", "sonar"]
    assert sorted(out[0].evidence) == ["e1", "e2"]


def test_deduplicate_sorts_by_severity_desc() -> None:
    dedup = FindingsDeduplicator()
    findings = [
        _finding("info", "fp-1", FindingSeverity.INFO, "sonar", ["i"]),
        _finding("critical", "fp-2", FindingSeverity.CRITICAL, "secrets", ["c"]),
        _finding("medium", "fp-3", FindingSeverity.MEDIUM, "sonar", ["m"]),
    ]

    out = dedup.deduplicate(findings)
    assert [finding.severity for finding in out] == [
        FindingSeverity.CRITICAL,
        FindingSeverity.MEDIUM,
        FindingSeverity.INFO,
    ]
