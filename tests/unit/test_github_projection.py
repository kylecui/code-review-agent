from agent_review.models.enums import Verdict
from agent_review.schemas.decision import ReviewDecision
from agent_review.scm.github_projection import project_decision


def _decision(verdict: Verdict) -> ReviewDecision:
    return ReviewDecision(
        verdict=verdict,
        confidence="high",
        blocking_findings=[],
        advisory_findings=[],
        escalation_reasons=[],
        missing_evidence=[],
        summary="summary",
    )


def test_all_verdicts_project_correctly() -> None:
    expected = {
        Verdict.PASS: ("success", "APPROVE"),
        Verdict.WARN: ("success", "COMMENT"),
        Verdict.REQUEST_CHANGES: ("failure", "REQUEST_CHANGES"),
        Verdict.BLOCK: ("failure", "REQUEST_CHANGES"),
        Verdict.ESCALATE: ("action_required", "COMMENT"),
    }

    for verdict, (conclusion, review_event) in expected.items():
        projection = project_decision(_decision(verdict))
        assert projection.check_run_conclusion == conclusion
        assert projection.review_event == review_event


def test_platform_projection_fields() -> None:
    projection = project_decision(_decision(Verdict.ESCALATE))
    assert isinstance(projection.check_run_conclusion, str)
    assert isinstance(projection.review_event, str)
    assert isinstance(projection.mentions, list)
