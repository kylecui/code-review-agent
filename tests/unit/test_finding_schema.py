from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_review.models.enums import (
    FindingConfidence,
    FindingDisposition,
    FindingSeverity,
)
from agent_review.schemas.finding import FindingCreate, FindingRead


def _valid_finding_create_data() -> dict[str, Any]:
    return {
        "finding_id": "SEC-AUTHZ-001",
        "category": "security.authz",
        "severity": FindingSeverity.HIGH,
        "confidence": FindingConfidence.MEDIUM,
        "blocking": True,
        "file_path": "src/app/authz.py",
        "line_start": 10,
        "line_end": 14,
        "source_tools": ["semgrep", "sonar"],
        "rule_id": "python.lang.security.authz.rule",
        "title": "Authorization bypass risk",
        "evidence": ["missing ownership check", "route lacks guard"],
        "impact": "Unauthorized users may access protected resources",
        "fix_recommendation": "Add ownership checks before serving data",
        "test_recommendation": "Add negative authz integration test",
        "fingerprint": "fp-1234",
        "disposition": FindingDisposition.NEW,
    }


def test_finding_create_valid_construction() -> None:
    finding = FindingCreate(**_valid_finding_create_data())

    assert finding.finding_id == "SEC-AUTHZ-001"
    assert finding.severity == FindingSeverity.HIGH
    assert finding.confidence == FindingConfidence.MEDIUM
    assert finding.disposition == FindingDisposition.NEW


@pytest.mark.parametrize(
    "missing_field",
    [
        "finding_id",
        "category",
        "severity",
        "confidence",
        "blocking",
        "file_path",
        "line_start",
        "source_tools",
        "title",
        "evidence",
        "impact",
        "fix_recommendation",
        "fingerprint",
    ],
)
def test_finding_create_missing_required_field_fails(missing_field: str) -> None:
    payload = _valid_finding_create_data()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        _ = FindingCreate(**payload)


def test_finding_create_allows_empty_lists_for_evidence_and_source_tools() -> None:
    payload = _valid_finding_create_data()
    payload["evidence"] = []
    payload["source_tools"] = []

    finding = FindingCreate(**payload)

    assert finding.evidence == []
    assert finding.source_tools == []


def test_finding_read_from_attributes() -> None:
    class FindingORM:
        id: object
        review_run_id: object
        created_at: object

        def __init__(self) -> None:
            self.id = uuid4()
            self.review_run_id = uuid4()
            self.created_at = datetime.now(UTC)
            for key, value in _valid_finding_create_data().items():
                setattr(self, key, value)

    model = FindingRead.model_validate(FindingORM())

    assert isinstance(model.id, type(uuid4()))
    assert model.finding_id == "SEC-AUTHZ-001"
    assert model.blocking is True
