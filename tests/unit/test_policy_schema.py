import pytest
from pydantic import ValidationError

from agent_review.models.enums import FailureMode
from agent_review.schemas.policy import (
    CollectorPolicyConfig,
    ExceptionsConfig,
    LimitsConfig,
    PolicyConfig,
    ProfilePolicyConfig,
)


def test_policy_config_valid_with_full_data() -> None:
    policy = PolicyConfig(
        version=2,
        collectors={
            "semgrep": CollectorPolicyConfig(
                failure_mode=FailureMode.DEGRADED,
                timeout_seconds=300,
                retries=2,
            )
        },
        profiles={
            "security_sensitive": ProfilePolicyConfig(
                require_checks=["ci/test", "ci/lint"],
                changed_lines_coverage_min=80,
                blocking_categories=["security\\..*"],
                escalate_categories=["crypto\\..*"],
                max_inline_comments=15,
            )
        },
        limits=LimitsConfig(
            max_inline_comments=30,
            max_summary_findings=20,
            max_diff_lines=20000,
        ),
        exceptions=ExceptionsConfig(emergency_bypass_labels=["emergency", "hotfix"]),
    )

    assert policy.version == 2
    assert policy.collectors["semgrep"].failure_mode == FailureMode.DEGRADED
    assert policy.profiles["security_sensitive"].require_checks == ["ci/test", "ci/lint"]
    assert policy.limits.max_summary_findings == 20
    assert policy.exceptions.emergency_bypass_labels == ["emergency", "hotfix"]


def test_policy_config_defaults() -> None:
    policy = PolicyConfig()

    assert policy.version == 1
    assert policy.collectors == {}
    assert policy.profiles == {}
    assert policy.limits == LimitsConfig()
    assert policy.exceptions == ExceptionsConfig()


def test_collector_policy_config_defaults() -> None:
    collector = CollectorPolicyConfig()

    assert collector.failure_mode == FailureMode.REQUIRED
    assert collector.timeout_seconds == 120
    assert collector.retries == 1


def test_profile_policy_config_defaults() -> None:
    profile = ProfilePolicyConfig()

    assert profile.require_checks == []
    assert profile.changed_lines_coverage_min is None
    assert profile.blocking_categories == []
    assert profile.escalate_categories == []
    assert profile.max_inline_comments == 25


def test_collector_policy_negative_timeout_is_allowed() -> None:
    collector = CollectorPolicyConfig(timeout_seconds=-1)
    assert collector.timeout_seconds == -1


def test_collector_policy_wrong_failure_mode_fails() -> None:
    with pytest.raises(ValidationError):
        _ = CollectorPolicyConfig.model_validate({"failure_mode": "invalid"})
