"""Format an AnalysisResult as a JSON-serialisable dictionary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_review.pipeline.analysis import AnalysisResult


def format_json_report(result: AnalysisResult) -> dict[str, Any]:
    return {
        "verdict": result.decision.verdict.value,
        "confidence": result.decision.confidence,
        "summary": result.decision.summary,
        "overall_risk": result.synthesis.overall_risk,
        "model_used": result.synthesis.model_used,
        "is_degraded": result.synthesis.is_degraded,
        "classification": result.classification.model_dump(mode="json"),
        "findings": [
            {
                "finding_id": f.finding_id,
                "category": f.category,
                "severity": f.severity.value,
                "confidence": f.confidence.value,
                "blocking": f.blocking,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "source_tools": f.source_tools,
                "rule_id": f.rule_id,
                "title": f.title,
                "impact": f.impact,
                "fix_recommendation": f.fix_recommendation,
                "fingerprint": f.fingerprint,
            }
            for f in result.findings
        ],
        "blocking_findings": result.decision.blocking_findings,
        "advisory_findings": result.decision.advisory_findings,
        "escalation_reasons": result.decision.escalation_reasons,
        "missing_evidence": result.decision.missing_evidence,
        "collector_results": [
            {
                "collector_name": cr.collector_name,
                "status": cr.status,
                "duration_ms": cr.duration_ms,
                "finding_count": len(cr.raw_findings),
                "error": cr.error,
            }
            for cr in result.collector_results
        ],
        "metrics": result.metrics.to_dict(),
    }
