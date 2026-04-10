from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from agent_review.models.enums import FindingSeverity

if TYPE_CHECKING:
    from agent_review.schemas.finding import FindingCreate


@dataclass(slots=True)
class PrioritizedFinding:
    finding_id: str
    priority: int
    explanation: str
    suggested_fix: str
    is_false_positive: bool


@dataclass(slots=True)
class SynthesisResult:
    prioritized_findings: list[PrioritizedFinding]
    summary: str
    overall_risk: str
    model_used: str
    cost_cents: float
    is_degraded: bool


class DegradedSynthesizer:
    _PRIORITY_MAP: ClassVar[dict[FindingSeverity, int]] = {
        FindingSeverity.CRITICAL: 1,
        FindingSeverity.HIGH: 2,
        FindingSeverity.MEDIUM: 3,
        FindingSeverity.LOW: 4,
        FindingSeverity.INFO: 5,
    }

    def synthesize(self, findings: list[FindingCreate]) -> SynthesisResult:
        prioritized = [
            PrioritizedFinding(
                finding_id=finding.finding_id,
                priority=self._PRIORITY_MAP[finding.severity],
                explanation=finding.impact,
                suggested_fix=finding.fix_recommendation,
                is_false_positive=False,
            )
            for finding in findings
        ]
        prioritized.sort(key=lambda finding: finding.priority)

        counts = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.HIGH: 0,
            FindingSeverity.MEDIUM: 0,
            FindingSeverity.LOW: 0,
            FindingSeverity.INFO: 0,
        }
        for finding in findings:
            counts[finding.severity] += 1

        summary = (
            f"Automated review found {len(findings)} findings: "
            f"{counts[FindingSeverity.CRITICAL]} critical, "
            f"{counts[FindingSeverity.HIGH]} high, "
            f"{counts[FindingSeverity.MEDIUM]} medium, "
            f"{counts[FindingSeverity.LOW]} low, "
            f"{counts[FindingSeverity.INFO]} info."
        )

        if counts[FindingSeverity.CRITICAL] > 0:
            overall_risk = "critical"
        elif counts[FindingSeverity.HIGH] > 0:
            overall_risk = "high"
        elif counts[FindingSeverity.MEDIUM] > 0:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return SynthesisResult(
            prioritized_findings=prioritized,
            summary=summary,
            overall_risk=overall_risk,
            model_used="deterministic",
            cost_cents=0.0,
            is_degraded=True,
        )
