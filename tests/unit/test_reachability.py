from __future__ import annotations

from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.normalize.reachability import ReachabilityAnalyzer
from agent_review.schemas.finding import FindingCreate


def _finding(
    *,
    finding_id: str,
    category: str,
    severity: FindingSeverity,
    file_path: str,
    rule_id: str,
    title: str,
    evidence: list[str],
) -> FindingCreate:
    return FindingCreate(
        finding_id=finding_id,
        category=category,
        severity=severity,
        confidence=FindingConfidence.MEDIUM,
        blocking=severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH},
        file_path=file_path,
        line_start=1,
        source_tools=["test"],
        rule_id=rule_id,
        title=title,
        evidence=evidence,
        impact="impact",
        fix_recommendation="fix",
        fingerprint=f"fp-{finding_id}",
    )


def test_tc_reach_001_analyze_no_sca_findings_returns_unchanged() -> None:
    analyzer = ReachabilityAnalyzer()
    findings = [
        _finding(
            finding_id="sast-1",
            category="security.sast",
            severity=FindingSeverity.HIGH,
            file_path="src/auth.py",
            rule_id="python.security.sql-injection",
            title="SAST finding",
            evidence=["unsafe query"],
        )
    ]

    out = analyzer.analyze(findings)

    assert out == findings


def test_tc_reach_002_analyze_matching_sast_evidence_preserves_sca_severity() -> None:
    analyzer = ReachabilityAnalyzer()
    sca = _finding(
        finding_id="sca-1",
        category="dependency.vulnerability",
        severity=FindingSeverity.HIGH,
        file_path="requirements.txt",
        rule_id="django-cve-2024-0001",
        title="Django vulnerable version",
        evidence=["package django has vulnerability"],
    )
    sast = _finding(
        finding_id="sast-1",
        category="security.sast",
        severity=FindingSeverity.MEDIUM,
        file_path="src/django/views.py",
        rule_id="python.security.call-django",
        title="Django usage",
        evidence=["imports django.shortcuts"],
    )

    out = analyzer.analyze([sca, sast])
    out_sca = next(f for f in out if f.finding_id == "sca-1")

    assert out_sca.severity == FindingSeverity.HIGH
    assert "(unreachable)" not in out_sca.title


def test_tc_reach_003_analyze_without_evidence_demotes_sca_severity() -> None:
    analyzer = ReachabilityAnalyzer()
    sca = _finding(
        finding_id="sca-1",
        category="sca.package",
        severity=FindingSeverity.CRITICAL,
        file_path="poetry.lock",
        rule_id="openssl-cve-2025-9999",
        title="OpenSSL vulnerable version",
        evidence=["package openssl vulnerable"],
    )
    sast = _finding(
        finding_id="sast-1",
        category="security.sast",
        severity=FindingSeverity.MEDIUM,
        file_path="src/app.py",
        rule_id="python.security.xss",
        title="XSS path",
        evidence=["tainted input"],
    )

    out = analyzer.analyze([sca, sast])
    out_sca = next(f for f in out if f.finding_id == "sca-1")

    assert out_sca.severity == FindingSeverity.HIGH
    assert out_sca.blocking is True
    assert out_sca.title.endswith("(unreachable)")


def test_tc_reach_004_identifies_dependency_prefix_as_sca() -> None:
    analyzer = ReachabilityAnalyzer()
    sca = _finding(
        finding_id="sca-1",
        category="dependency.runtime",
        severity=FindingSeverity.MEDIUM,
        file_path="requirements.txt",
        rule_id="requests-cve",
        title="Requests vulnerable",
        evidence=["requests package vulnerable"],
    )
    non_sca = _finding(
        finding_id="sast-1",
        category="security.sast",
        severity=FindingSeverity.LOW,
        file_path="src/a.py",
        rule_id="python.security.rule",
        title="SAST",
        evidence=["xss"],
    )

    out = analyzer.analyze([sca, non_sca])
    out_sca = next(f for f in out if f.finding_id == "sca-1")

    assert out_sca.title.endswith("(unreachable)")


def test_tc_reach_005_preserves_non_sca_findings_untouched() -> None:
    analyzer = ReachabilityAnalyzer()
    non_sca = _finding(
        finding_id="sast-1",
        category="security.sast",
        severity=FindingSeverity.LOW,
        file_path="src/a.py",
        rule_id="python.security.rule",
        title="Original SAST",
        evidence=["evidence"],
    )
    sca = _finding(
        finding_id="sca-1",
        category="dependency.vulnerability",
        severity=FindingSeverity.MEDIUM,
        file_path="requirements.txt",
        rule_id="urllib3-cve",
        title="urllib3 vuln",
        evidence=["urllib3 issue"],
    )

    out = analyzer.analyze([non_sca, sca])
    out_non_sca = next(f for f in out if f.finding_id == "sast-1")

    assert out_non_sca == non_sca


def test_tc_reach_006_analyze_empty_findings_returns_empty() -> None:
    analyzer = ReachabilityAnalyzer()

    out = analyzer.analyze([])

    assert out == []
