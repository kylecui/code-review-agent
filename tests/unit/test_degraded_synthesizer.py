from __future__ import annotations

from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.reasoning.degraded import DegradedSynthesizer
from agent_review.schemas.finding import FindingCreate


def _finding(finding_id: str, severity: FindingSeverity) -> FindingCreate:
    return FindingCreate(
        finding_id=finding_id,
        category="quality.issue",
        severity=severity,
        confidence=FindingConfidence.MEDIUM,
        blocking=severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH},
        file_path="src/a.py",
        line_start=1,
        source_tools=["tool"],
        title=finding_id,
        evidence=["e"],
        impact="impact",
        fix_recommendation="fix",
        fingerprint=f"fp-{finding_id}",
    )


def test_degraded_priority_mapping_and_sorting() -> None:
    synth = DegradedSynthesizer()
    result = synth.synthesize(
        [
            _finding("low", FindingSeverity.LOW),
            _finding("critical", FindingSeverity.CRITICAL),
            _finding("high", FindingSeverity.HIGH),
        ]
    )

    assert [item.finding_id for item in result.prioritized_findings] == ["critical", "high", "low"]
    assert [item.priority for item in result.prioritized_findings] == [1, 2, 4]


def test_degraded_summary_and_flags() -> None:
    synth = DegradedSynthesizer()
    result = synth.synthesize([_finding("critical", FindingSeverity.CRITICAL)])

    assert "Automated review found 1 findings: 1 critical" in result.summary
    assert result.overall_risk == "critical"
    assert result.is_degraded is True
    assert result.model_used == "deterministic"
    assert result.cost_cents == 0.0
