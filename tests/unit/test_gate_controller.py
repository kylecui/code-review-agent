from __future__ import annotations

from typing import TYPE_CHECKING, cast

from agent_review.collectors.base import CollectorResult
from agent_review.gate.controller import GateController
from agent_review.models.enums import FailureMode, FindingConfidence, FindingSeverity, Verdict
from agent_review.reasoning.degraded import SynthesisResult
from agent_review.schemas.classification import Classification
from agent_review.schemas.finding import FindingCreate
from agent_review.schemas.policy import (
    CollectorPolicyConfig,
    ExceptionsConfig,
    PolicyConfig,
    ProfilePolicyConfig,
)

if TYPE_CHECKING:
    from agent_review.collectors.base import CollectorStatus


def _finding(
    finding_id: str,
    *,
    category: str,
    severity: FindingSeverity = FindingSeverity.LOW,
    blocking: bool = False,
) -> FindingCreate:
    return FindingCreate(
        finding_id=finding_id,
        category=category,
        severity=severity,
        confidence=FindingConfidence.HIGH,
        blocking=blocking,
        file_path="src/app.py",
        line_start=1,
        source_tools=["tool"],
        title=finding_id,
        evidence=["evidence"],
        impact="impact",
        fix_recommendation="fix",
        fingerprint=f"fp-{finding_id}",
    )


def _synthesis(*, is_degraded: bool = False, overall_risk: str = "medium") -> SynthesisResult:
    return SynthesisResult(
        prioritized_findings=[],
        summary="Synth summary",
        overall_risk=overall_risk,
        model_used="deterministic",
        cost_cents=0.0,
        is_degraded=is_degraded,
    )


def _classification(profiles: list[str] | None = None) -> Classification:
    return Classification(
        change_type="code",
        domains=["backend"],
        risk_level="medium",
        profiles=profiles or ["core_quality"],
        file_categories={},
    )


def _policy() -> PolicyConfig:
    return PolicyConfig(
        collectors={
            "semgrep": CollectorPolicyConfig(failure_mode=FailureMode.REQUIRED),
            "github_ci": CollectorPolicyConfig(failure_mode=FailureMode.DEGRADED),
            "sonar": CollectorPolicyConfig(failure_mode=FailureMode.OPTIONAL),
        },
        profiles={
            "core_quality": ProfilePolicyConfig(
                blocking_categories=["security.*", "quality.bug"],
                escalate_categories=["quality.code-smell"],
            ),
            "workflow_security": ProfilePolicyConfig(
                blocking_categories=["security.*"],
                escalate_categories=["quality.*"],
            ),
        },
        exceptions=ExceptionsConfig(emergency_bypass_labels=["emergency-bypass", "hotfix"]),
    )


def _collector_result(name: str, status: str) -> CollectorResult:
    return CollectorResult(
        collector_name=name,
        status=cast("CollectorStatus", status),
        raw_findings=[],
        duration_ms=10,
    )


def test_verdict_pass_with_no_findings() -> None:
    controller = GateController()

    decision = controller.evaluate(
        findings=[],
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[
            _collector_result("semgrep", "success"),
            _collector_result("github_ci", "success"),
        ],
    )

    assert decision.verdict == Verdict.PASS
    assert decision.blocking_findings == []
    assert decision.advisory_findings == []


def test_verdict_warn_with_only_advisory_findings() -> None:
    controller = GateController()
    findings = [_finding("f1", category="style.whitespace", severity=FindingSeverity.LOW)]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.WARN
    assert decision.blocking_findings == []
    assert decision.advisory_findings == ["f1"]


def test_verdict_request_changes_for_non_critical_blocking() -> None:
    controller = GateController()
    findings = [_finding("f1", category="quality.bug", severity=FindingSeverity.HIGH)]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.REQUEST_CHANGES
    assert decision.blocking_findings == ["f1"]


def test_verdict_block_for_critical_blocking_findings() -> None:
    controller = GateController()
    findings = [
        _finding(
            "f1",
            category="security.sast",
            severity=FindingSeverity.CRITICAL,
            blocking=True,
        )
    ]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(overall_risk="critical"),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.BLOCK
    assert decision.blocking_findings == ["f1"]


def test_verdict_escalate_when_escalation_category_matches() -> None:
    controller = GateController()
    findings = [_finding("f1", category="quality.code-smell", severity=FindingSeverity.LOW)]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.ESCALATE
    assert decision.escalation_reasons == ["Category quality.code-smell requires escalation"]


def test_emergency_bypass_short_circuit() -> None:
    controller = GateController()
    findings = [
        _finding("f1", category="security.sast", severity=FindingSeverity.CRITICAL, blocking=True)
    ]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "failure")],
        pr_labels=["HotFix"],
    )

    assert decision.verdict == Verdict.WARN
    assert decision.summary == "Emergency bypass activated"
    assert decision.missing_evidence == []


def test_required_collector_failure_blocks() -> None:
    controller = GateController()

    decision = controller.evaluate(
        findings=[],
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "timeout")],
    )

    assert decision.verdict == Verdict.BLOCK
    assert decision.missing_evidence == ["semgrep"]


def test_degraded_collector_failure_warns_not_blocks() -> None:
    controller = GateController()

    decision = controller.evaluate(
        findings=[],
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[
            _collector_result("semgrep", "success"),
            _collector_result("github_ci", "failure"),
        ],
    )

    assert decision.verdict == Verdict.WARN
    assert "Collector evidence degraded: github_ci." in decision.summary


def test_optional_collector_failure_has_no_effect() -> None:
    controller = GateController()

    decision = controller.evaluate(
        findings=[],
        synthesis=_synthesis(),
        classification=_classification(),
        policy=_policy(),
        collector_results=[
            _collector_result("semgrep", "success"),
            _collector_result("github_ci", "success"),
            _collector_result("sonar", "failure"),
        ],
    )

    assert decision.verdict == Verdict.PASS
    assert decision.missing_evidence == []


def test_category_glob_matching_for_security_patterns() -> None:
    controller = GateController()
    findings = [
        _finding("f1", category="security.secret-detection", severity=FindingSeverity.MEDIUM)
    ]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(profiles=["workflow_security"]),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.REQUEST_CHANGES
    assert decision.blocking_findings == ["f1"]


def test_blocking_categories_applied_from_applicable_profiles_only() -> None:
    controller = GateController()
    findings = [_finding("f1", category="quality.bug", severity=FindingSeverity.MEDIUM)]

    decision = controller.evaluate(
        findings=findings,
        synthesis=_synthesis(),
        classification=_classification(profiles=["workflow_security"]),
        policy=_policy(),
        collector_results=[_collector_result("semgrep", "success")],
    )

    assert decision.verdict == Verdict.ESCALATE
    assert decision.blocking_findings == []
    assert decision.escalation_reasons == ["Category quality.bug requires escalation"]
