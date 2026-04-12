import datetime as dt
import uuid
from typing import Any

from agent_review.models import Finding, ReviewRun, ReviewState, RunKind, TriggerEvent
from agent_review.models.enums import FindingConfidence, FindingDisposition, FindingSeverity


def build_review_run(**overrides: Any) -> ReviewRun:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "repo": "owner/repo",
        "run_kind": RunKind.PR,
        "pr_number": 1,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "installation_id": 12345,
        "attempt": 1,
        "state": ReviewState.PENDING,
        "trigger_event": TriggerEvent.OPENED,
        "delivery_id": str(uuid.uuid4()),
        "created_at": dt.datetime.now(dt.UTC),
        "updated_at": dt.datetime.now(dt.UTC),
    }
    defaults.update(overrides)
    return ReviewRun(**defaults)


def build_finding(review_run_id: uuid.UUID | None = None, **overrides: Any) -> Finding:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "review_run_id": review_run_id or uuid.uuid4(),
        "finding_id": "TEST-001",
        "category": "test.category",
        "severity": FindingSeverity.MEDIUM,
        "confidence": FindingConfidence.HIGH,
        "blocking": False,
        "file_path": "src/example.py",
        "line_start": 10,
        "line_end": None,
        "source_tools": ["test_tool"],
        "rule_id": None,
        "title": "Test Finding",
        "evidence": ["evidence item"],
        "impact": "Test impact",
        "fix_recommendation": "Fix this",
        "test_recommendation": None,
        "fingerprint": "test-fingerprint-" + str(uuid.uuid4())[:8],
        "disposition": FindingDisposition.NEW,
        "created_at": dt.datetime.now(dt.UTC),
    }
    defaults.update(overrides)
    return Finding(**defaults)
