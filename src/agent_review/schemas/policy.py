from pydantic import BaseModel, Field

from agent_review.models.enums import FailureMode


class CollectorPolicyConfig(BaseModel):
    failure_mode: FailureMode = FailureMode.REQUIRED
    timeout_seconds: int = 120
    retries: int = 1


class ProfilePolicyConfig(BaseModel):
    require_checks: list[str] = Field(default_factory=list)
    changed_lines_coverage_min: int | None = None
    blocking_categories: list[str] = Field(default_factory=list)
    escalate_categories: list[str] = Field(default_factory=list)
    max_inline_comments: int = 25


class LimitsConfig(BaseModel):
    max_inline_comments: int = 25
    max_summary_findings: int = 10
    max_diff_lines: int = 10000


class ExceptionsConfig(BaseModel):
    emergency_bypass_labels: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    version: int = 1
    collectors: dict[str, CollectorPolicyConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfilePolicyConfig] = Field(default_factory=dict)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    exceptions: ExceptionsConfig = Field(default_factory=ExceptionsConfig)
