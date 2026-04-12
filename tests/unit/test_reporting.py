from __future__ import annotations

from agent_review.collectors.base import CollectorResult
from agent_review.models.enums import FindingConfidence, FindingSeverity, Verdict
from agent_review.observability import RunMetrics
from agent_review.pipeline.analysis import AnalysisResult
from agent_review.reasoning.degraded import SynthesisResult
from agent_review.reporting.github_issue import _build_issue_body
from agent_review.reporting.json_report import format_json_report
from agent_review.schemas.classification import Classification
from agent_review.schemas.decision import ReviewDecision
from agent_review.schemas.finding import FindingCreate
from agent_review.schemas.policy import PolicyConfig


def _make_analysis_result() -> AnalysisResult:
    classification = Classification(
        change_type="code",
        domains=["backend"],
        risk_level="low",
        profiles=["core_quality"],
        file_categories={},
    )
    finding = FindingCreate(
        finding_id="f-1",
        category="security.issue",
        severity=FindingSeverity.MEDIUM,
        confidence=FindingConfidence.HIGH,
        blocking=False,
        file_path="src/app.py",
        line_start=10,
        source_tools=["semgrep"],
        title="SQL injection risk",
        evidence=["user input flows to query"],
        impact="data leak",
        fix_recommendation="use parameterized queries",
        fingerprint="fp-1",
    )
    synthesis = SynthesisResult(
        prioritized_findings=[],
        summary="one medium finding",
        overall_risk="medium",
        model_used="deterministic",
        cost_cents=0.0,
        is_degraded=False,
    )
    decision = ReviewDecision(
        verdict=Verdict.WARN,
        confidence="high",
        blocking_findings=[],
        advisory_findings=["f-1"],
        escalation_reasons=[],
        missing_evidence=[],
        summary="advisory only",
    )
    collector_results = [
        CollectorResult(
            collector_name="semgrep",
            status="success",
            raw_findings=[{"id": "raw-1"}],
            duration_ms=42,
        )
    ]
    metrics = RunMetrics(run_id="test")
    return AnalysisResult(
        classification=classification,
        findings=[finding],
        synthesis=synthesis,
        decision=decision,
        collector_results=collector_results,
        policy=PolicyConfig(),
        metrics=metrics,
    )


def test_format_json_report() -> None:
    result = _make_analysis_result()
    report = format_json_report(result)

    assert report["verdict"] == "warn"
    assert report["confidence"] == "high"
    assert report["summary"] == "advisory only"
    assert isinstance(report["findings"], list)
    assert len(report["findings"]) == 1

    f = report["findings"][0]
    assert f["finding_id"] == "f-1"
    assert f["severity"] == "medium"
    assert f["file_path"] == "src/app.py"
    assert f["title"] == "SQL injection risk"
    assert f["fingerprint"] == "fp-1"

    assert isinstance(report["collector_results"], list)
    assert len(report["collector_results"]) == 1
    assert report["collector_results"][0]["collector_name"] == "semgrep"

    assert isinstance(report["metrics"], dict)
    assert report["metrics"]["run_id"] == "test"


def test_build_issue_body() -> None:
    result = _make_analysis_result()
    body = _build_issue_body(result, "owner/repo")

    assert "## Baseline Scan" in body
    assert "warn" in body
    assert "Findings (1)" in body
    assert "SQL injection risk" in body
    assert "semgrep" in body
