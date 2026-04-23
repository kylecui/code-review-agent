from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from agent_review.models.enums import FindingSeverity
from agent_review.observability import get_logger
from agent_review.schemas.finding import FindingCreate

logger = get_logger(__name__)


@dataclass(slots=True)
class ReachabilityResult:
    reachable_findings: list[FindingCreate]
    unreachable_findings: list[FindingCreate]
    total_filtered: int


class ReachabilityAnalyzer:
    _SEVERITY_DEMOTION_MAP: dict[FindingSeverity, FindingSeverity] = {
        FindingSeverity.CRITICAL: FindingSeverity.HIGH,
        FindingSeverity.HIGH: FindingSeverity.MEDIUM,
        FindingSeverity.MEDIUM: FindingSeverity.LOW,
        FindingSeverity.LOW: FindingSeverity.INFO,
        FindingSeverity.INFO: FindingSeverity.INFO,
    }

    def analyze(
        self,
        findings: list[FindingCreate],
        sca_findings: list[FindingCreate] | None = None,
    ) -> list[FindingCreate]:
        if not findings and not sca_findings:
            return []

        detected_sca_findings = [finding for finding in findings if self._is_sca_finding(finding)]
        sast_findings = [finding for finding in findings if not self._is_sca_finding(finding)]

        target_sca_findings = sca_findings if sca_findings is not None else detected_sca_findings
        if not target_sca_findings:
            return findings

        if sca_findings is None:
            output: list[FindingCreate] = []
            for finding in findings:
                if not self._is_sca_finding(finding):
                    output.append(finding)
                    continue
                output.append(self._process_sca_finding(finding, sast_findings))
            return output

        output = list(sast_findings)
        for sca_finding in target_sca_findings:
            output.append(self._process_sca_finding(sca_finding, sast_findings))
        return output

    def _process_sca_finding(
        self,
        sca_finding: FindingCreate,
        sast_findings: list[FindingCreate],
    ) -> FindingCreate:
        if self._find_call_evidence(sca_finding, sast_findings):
            return sca_finding

        demoted_severity = self._SEVERITY_DEMOTION_MAP[sca_finding.severity]
        title = sca_finding.title
        if "(unreachable)" not in title:
            title = f"{title} (unreachable)"

        logger.debug(
            "sca_finding_demoted_unreachable",
            finding_id=sca_finding.finding_id,
            original_severity=sca_finding.severity.value,
            demoted_severity=demoted_severity.value,
        )

        return sca_finding.model_copy(
            update={
                "severity": demoted_severity,
                "blocking": demoted_severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH},
                "title": title,
            }
        )

    @staticmethod
    def _is_sca_finding(finding: FindingCreate) -> bool:
        category = finding.category.lower()
        return category.startswith("dependency.") or category.startswith("sca.")

    def _find_call_evidence(
        self,
        sca_finding: FindingCreate,
        sast_findings: list[FindingCreate],
    ) -> bool:
        if not sast_findings:
            return False

        search_terms = self._extract_search_terms(sca_finding)
        if not search_terms:
            return False

        for finding in sast_findings:
            context = " ".join(
                [
                    finding.file_path,
                    finding.rule_id or "",
                    " ".join(finding.evidence),
                ]
            ).lower()
            if any(term in context for term in search_terms):
                return True
        return False

    @staticmethod
    def _extract_search_terms(sca_finding: FindingCreate) -> set[str]:
        raw_text = " ".join([sca_finding.rule_id or "", " ".join(sca_finding.evidence)]).lower()
        tokens = cast("list[str]", re.findall(r"[a-z0-9_.-]+", raw_text))

        search_terms: set[str] = set()
        for token in tokens:
            if len(token) >= 3:
                search_terms.add(token)

            parts = re.split(r"[._-]", token)
            for part in parts:
                if len(part) >= 3:
                    search_terms.add(part)

        return search_terms
