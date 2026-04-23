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
    fingerprint_v2: str | None = None,
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
        fingerprint_v2=fingerprint_v2,
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


def test_deduplicate_groups_by_fingerprint_v2_when_present() -> None:
    dedup = FindingsDeduplicator()
    findings = [
        _finding(
            "a", "fp-old-1", FindingSeverity.MEDIUM, "semgrep", ["e1"], fingerprint_v2="fp-v2-1"
        ),
        _finding(
            "b", "fp-old-2", FindingSeverity.HIGH, "spotbugs", ["e2"], fingerprint_v2="fp-v2-1"
        ),
        _finding("c", "fp-old-3", FindingSeverity.LOW, "sonar", ["e3"]),
    ]

    out = dedup.deduplicate(findings)

    assert len(out) == 2
    merged = next(f for f in out if f.severity == FindingSeverity.HIGH)
    assert sorted(merged.source_tools) == ["semgrep", "spotbugs"]
    assert sorted(merged.evidence) == ["e1", "e2"]


def test_deduplicate_v2_takes_priority_over_v1() -> None:
    """Two findings share fingerprint but have different fingerprint_v2 → NOT merged."""
    dedup = FindingsDeduplicator()
    findings = [
        _finding("a", "fp-same", FindingSeverity.MEDIUM, "semgrep", ["e1"], fingerprint_v2="v2-a"),
        _finding("b", "fp-same", FindingSeverity.HIGH, "sonar", ["e2"], fingerprint_v2="v2-b"),
    ]

    out = dedup.deduplicate(findings)

    assert len(out) == 2


def test_deduplicate_mixed_v1_and_v2_fingerprints() -> None:
    """Findings without v2 fall back to v1 grouping."""
    dedup = FindingsDeduplicator()
    findings = [
        _finding("a", "fp-1", FindingSeverity.MEDIUM, "semgrep", ["e1"]),
        _finding("b", "fp-1", FindingSeverity.LOW, "sonar", ["e2"]),
        _finding("c", "fp-2", FindingSeverity.HIGH, "gitleaks", ["e3"], fingerprint_v2="fp-v2-x"),
    ]

    out = dedup.deduplicate(findings)

    assert len(out) == 2
    v1_merged = next(f for f in out if f.finding_id in ("a", "b"))
    assert sorted(v1_merged.source_tools) == ["semgrep", "sonar"]
