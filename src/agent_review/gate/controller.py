from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING

from agent_review.models.enums import FailureMode, FindingSeverity, Verdict
from agent_review.schemas.decision import ReviewDecision

if TYPE_CHECKING:
    from agent_review.collectors.base import CollectorResult
    from agent_review.reasoning.degraded import SynthesisResult
    from agent_review.schemas.classification import Classification
    from agent_review.schemas.finding import FindingCreate
    from agent_review.schemas.policy import PolicyConfig


class GateController:
    def evaluate(
        self,
        findings: list[FindingCreate],
        synthesis: SynthesisResult,
        classification: Classification,
        policy: PolicyConfig,
        collector_results: list[CollectorResult],
        pr_labels: list[str] | None = None,
    ) -> ReviewDecision:
        if self._is_emergency_bypass(pr_labels or [], policy):
            return ReviewDecision(
                verdict=Verdict.WARN,
                confidence="high",
                blocking_findings=[],
                advisory_findings=[finding.finding_id for finding in findings],
                escalation_reasons=[],
                missing_evidence=[],
                summary="Emergency bypass activated",
            )

        required_failed_collectors, degraded_collectors = self._evaluate_collector_failures(
            policy=policy,
            collector_results=collector_results,
        )
        if required_failed_collectors:
            return ReviewDecision(
                verdict=Verdict.BLOCK,
                confidence="high",
                blocking_findings=[],
                advisory_findings=[finding.finding_id for finding in findings],
                escalation_reasons=[],
                missing_evidence=required_failed_collectors,
                summary=self._build_summary(
                    synthesis=synthesis,
                    required_failed_collectors=required_failed_collectors,
                    degraded_collectors=degraded_collectors,
                ),
            )

        blocking_patterns, escalate_patterns = self._collect_profile_patterns(
            policy=policy,
            classification=classification,
        )

        blocking_findings: list[FindingCreate] = []
        escalation_findings: list[FindingCreate] = []

        for finding in findings:
            category_is_blocking = any(
                fnmatch(finding.category, pattern) for pattern in blocking_patterns
            )
            if finding.blocking or category_is_blocking:
                blocking_findings.append(finding)

            if any(fnmatch(finding.category, pattern) for pattern in escalate_patterns):
                escalation_findings.append(finding)

        verdict = self._determine_verdict(
            blocking_findings=blocking_findings,
            escalation_findings=escalation_findings,
            all_findings=findings,
            has_degraded_collectors=bool(degraded_collectors),
        )
        blocking_ids = {blocking.finding_id for blocking in blocking_findings}
        advisory_findings = [
            finding.finding_id for finding in findings if finding.finding_id not in blocking_ids
        ]

        return ReviewDecision(
            verdict=verdict,
            confidence=synthesis.overall_risk,
            blocking_findings=[finding.finding_id for finding in blocking_findings],
            advisory_findings=advisory_findings,
            escalation_reasons=[
                f"Category {finding.category} requires escalation"
                for finding in escalation_findings
            ],
            missing_evidence=required_failed_collectors,
            summary=self._build_summary(
                synthesis=synthesis,
                required_failed_collectors=required_failed_collectors,
                degraded_collectors=degraded_collectors,
            ),
        )

    @staticmethod
    def _is_emergency_bypass(labels: list[str], policy: PolicyConfig) -> bool:
        normalized_labels = {label.strip().lower() for label in labels if label.strip()}
        bypass_labels = {
            label.strip().lower()
            for label in policy.exceptions.emergency_bypass_labels
            if label.strip()
        }
        return bool(normalized_labels.intersection(bypass_labels))

    @staticmethod
    def _evaluate_collector_failures(
        policy: PolicyConfig, collector_results: list[CollectorResult]
    ) -> tuple[list[str], list[str]]:
        result_by_name = {result.collector_name: result for result in collector_results}
        required_failures: list[str] = []
        degraded_collectors: list[str] = []

        for collector_name, config in policy.collectors.items():
            result = result_by_name.get(collector_name)
            is_success = result is not None and result.status == "success"

            if is_success:
                continue

            if config.failure_mode == FailureMode.REQUIRED:
                required_failures.append(collector_name)
            elif config.failure_mode == FailureMode.DEGRADED:
                degraded_collectors.append(collector_name)

        return required_failures, degraded_collectors

    @staticmethod
    def _collect_profile_patterns(
        policy: PolicyConfig, classification: Classification
    ) -> tuple[list[str], list[str]]:
        blocking_patterns: list[str] = []
        escalate_patterns: list[str] = []

        for profile_name in classification.profiles:
            profile = policy.profiles.get(profile_name)
            if profile is None:
                continue
            blocking_patterns.extend(profile.blocking_categories)
            escalate_patterns.extend(profile.escalate_categories)

        return blocking_patterns, escalate_patterns

    @staticmethod
    def _determine_verdict(
        blocking_findings: list[FindingCreate],
        escalation_findings: list[FindingCreate],
        all_findings: list[FindingCreate],
        has_degraded_collectors: bool,
    ) -> Verdict:
        if blocking_findings and any(
            finding.severity == FindingSeverity.CRITICAL for finding in blocking_findings
        ):
            return Verdict.BLOCK
        if blocking_findings:
            return Verdict.REQUEST_CHANGES
        if escalation_findings:
            return Verdict.ESCALATE
        if all_findings:
            return Verdict.WARN
        if has_degraded_collectors:
            return Verdict.WARN
        return Verdict.PASS

    @staticmethod
    def _build_summary(
        synthesis: SynthesisResult,
        required_failed_collectors: list[str],
        degraded_collectors: list[str],
    ) -> str:
        parts = [synthesis.summary]
        if synthesis.is_degraded:
            parts.append("Synthesis ran in degraded mode.")
        if required_failed_collectors:
            parts.append(
                "Required collectors failed: " + ", ".join(sorted(required_failed_collectors)) + "."
            )
        if degraded_collectors:
            parts.append(
                "Collector evidence degraded: " + ", ".join(sorted(degraded_collectors)) + "."
            )
        return " ".join(part for part in parts if part)
