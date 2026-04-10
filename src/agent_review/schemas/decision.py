from pydantic import BaseModel

from agent_review.models.enums import Verdict


class ReviewDecision(BaseModel):
    verdict: Verdict
    confidence: str
    blocking_findings: list[str]
    advisory_findings: list[str]
    escalation_reasons: list[str]
    missing_evidence: list[str]
    summary: str


class PlatformProjection(BaseModel):
    check_run_conclusion: str
    review_event: str
    mentions: list[str]
