from agent_review.models.enums import (
    FailureMode,
    FindingConfidence,
    FindingDisposition,
    FindingSeverity,
    ReviewState,
    TriggerEvent,
    Verdict,
)


def test_review_state_values() -> None:
    assert ReviewState.PENDING.value == "pending"
    assert ReviewState.CLASSIFYING.value == "classifying"
    assert ReviewState.COLLECTING.value == "collecting"
    assert ReviewState.NORMALIZING.value == "normalizing"
    assert ReviewState.REASONING.value == "reasoning"
    assert ReviewState.DECIDING.value == "deciding"
    assert ReviewState.PUBLISHING.value == "publishing"
    assert ReviewState.COMPLETED.value == "completed"
    assert ReviewState.FAILED.value == "failed"
    assert ReviewState.SUPERSEDED.value == "superseded"


def test_verdict_values() -> None:
    assert Verdict.PASS.value == "pass"
    assert Verdict.WARN.value == "warn"
    assert Verdict.REQUEST_CHANGES.value == "request_changes"
    assert Verdict.BLOCK.value == "block"
    assert Verdict.ESCALATE.value == "escalate"


def test_failure_mode_values() -> None:
    assert FailureMode.REQUIRED.value == "required"
    assert FailureMode.OPTIONAL.value == "optional"
    assert FailureMode.DEGRADED.value == "degraded"


def test_trigger_event_values() -> None:
    assert TriggerEvent.OPENED.value == "opened"
    assert TriggerEvent.SYNCHRONIZE.value == "synchronize"
    assert TriggerEvent.READY_FOR_REVIEW.value == "ready_for_review"


def test_finding_severity_values() -> None:
    assert FindingSeverity.CRITICAL.value == "critical"
    assert FindingSeverity.HIGH.value == "high"
    assert FindingSeverity.MEDIUM.value == "medium"
    assert FindingSeverity.LOW.value == "low"
    assert FindingSeverity.INFO.value == "info"


def test_finding_confidence_values() -> None:
    assert FindingConfidence.HIGH.value == "high"
    assert FindingConfidence.MEDIUM.value == "medium"
    assert FindingConfidence.LOW.value == "low"


def test_finding_disposition_values() -> None:
    assert FindingDisposition.NEW.value == "new"
    assert FindingDisposition.EXISTING.value == "existing"
    assert FindingDisposition.FIXED.value == "fixed"


def test_string_comparison() -> None:
    assert ReviewState.PENDING == "pending"
