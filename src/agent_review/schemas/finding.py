import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from agent_review.models.enums import (
    FindingConfidence,
    FindingDisposition,
    FindingSeverity,
)


class FindingCreate(BaseModel):
    finding_id: str
    category: str
    severity: FindingSeverity
    confidence: FindingConfidence
    blocking: bool
    file_path: str
    line_start: int
    line_end: int | None = None
    source_tools: list[str]
    rule_id: str | None = None
    title: str
    evidence: list[str]
    impact: str
    fix_recommendation: str
    test_recommendation: str | None = None
    fingerprint: str
    disposition: FindingDisposition = FindingDisposition.NEW


class FindingRead(FindingCreate):
    id: uuid.UUID
    review_run_id: uuid.UUID
    created_at: datetime

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)
