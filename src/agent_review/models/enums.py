from enum import Enum

_Enum = Enum


class ReviewState(str, _Enum):
    PENDING = "pending"
    CLASSIFYING = "classifying"
    COLLECTING = "collecting"
    NORMALIZING = "normalizing"
    REASONING = "reasoning"
    DECIDING = "deciding"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class Verdict(str, _Enum):
    PASS = "pass"
    WARN = "warn"
    REQUEST_CHANGES = "request_changes"
    BLOCK = "block"
    ESCALATE = "escalate"


class FailureMode(str, _Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    DEGRADED = "degraded"


class TriggerEvent(str, _Enum):
    OPENED = "opened"
    SYNCHRONIZE = "synchronize"
    READY_FOR_REVIEW = "ready_for_review"


class FindingSeverity(str, _Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingConfidence(str, _Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RunKind(str, _Enum):
    PR = "pr"
    BASELINE = "baseline"


class FindingDisposition(str, _Enum):
    NEW = "new"
    EXISTING = "existing"
    FIXED = "fixed"
