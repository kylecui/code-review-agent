from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from agent_review.models.enums import FindingSeverity

if TYPE_CHECKING:
    from agent_review.schemas.finding import FindingCreate

_SEVERITY_RANK: dict[FindingSeverity, int] = {
    FindingSeverity.CRITICAL: 5,
    FindingSeverity.HIGH: 4,
    FindingSeverity.MEDIUM: 3,
    FindingSeverity.LOW: 2,
    FindingSeverity.INFO: 1,
}


class FindingsDeduplicator:
    def deduplicate(self, findings: list[FindingCreate]) -> list[FindingCreate]:
        grouped: dict[str, list[FindingCreate]] = defaultdict(list)
        for finding in findings:
            grouped[finding.fingerprint].append(finding)

        deduplicated: list[FindingCreate] = []
        for group in grouped.values():
            deduplicated.append(self._merge_group(group))

        deduplicated.sort(key=lambda finding: _SEVERITY_RANK[finding.severity], reverse=True)
        return deduplicated

    def _merge_group(self, group: list[FindingCreate]) -> FindingCreate:
        if len(group) == 1:
            return group[0]

        primary = max(group, key=lambda finding: _SEVERITY_RANK[finding.severity])
        merged_source_tools: list[str] = []
        for finding in group:
            for source_tool in finding.source_tools:
                if source_tool not in merged_source_tools:
                    merged_source_tools.append(source_tool)

        merged_evidence: list[str] = []
        for finding in group:
            for evidence_item in finding.evidence:
                if evidence_item not in merged_evidence:
                    merged_evidence.append(evidence_item)

        highest_severity = max(group, key=lambda finding: _SEVERITY_RANK[finding.severity]).severity

        return primary.model_copy(
            update={
                "severity": highest_severity,
                "blocking": highest_severity
                in {
                    FindingSeverity.CRITICAL,
                    FindingSeverity.HIGH,
                },
                "source_tools": merged_source_tools,
                "evidence": merged_evidence,
            }
        )
