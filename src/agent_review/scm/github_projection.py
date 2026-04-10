from agent_review.models.enums import Verdict
from agent_review.schemas.decision import PlatformProjection, ReviewDecision

CONCLUSION_MAP: dict[Verdict, str] = {
    Verdict.PASS: "success",
    Verdict.WARN: "success",
    Verdict.REQUEST_CHANGES: "failure",
    Verdict.BLOCK: "failure",
    Verdict.ESCALATE: "action_required",
}

REVIEW_EVENT_MAP: dict[Verdict, str] = {
    Verdict.PASS: "APPROVE",
    Verdict.WARN: "COMMENT",
    Verdict.REQUEST_CHANGES: "REQUEST_CHANGES",
    Verdict.BLOCK: "REQUEST_CHANGES",
    Verdict.ESCALATE: "COMMENT",
}


def project_decision(decision: ReviewDecision) -> PlatformProjection:
    return PlatformProjection(
        check_run_conclusion=CONCLUSION_MAP[decision.verdict],
        review_event=REVIEW_EVENT_MAP[decision.verdict],
        mentions=[],
    )
