"""Format an AnalysisResult as a detailed Markdown report."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent_review.models.enums import FindingSeverity

if TYPE_CHECKING:
    from agent_review.pipeline.analysis import AnalysisResult
    from agent_review.schemas.finding import FindingCreate


_SEVERITY_ICON: dict[str, str] = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}


def _severity_icon(severity: FindingSeverity) -> str:
    return _SEVERITY_ICON.get(severity.value, "⚪")


def _severity_counts(findings: list[FindingCreate]) -> dict[FindingSeverity, int]:
    counts: dict[FindingSeverity, int] = {s: 0 for s in FindingSeverity}
    for f in findings:
        counts[f.severity] += 1
    return counts


def _format_finding(idx: int, f: FindingCreate) -> str:
    icon = _severity_icon(f.severity)
    lines: list[str] = []
    lines.append(f"### {idx}. {icon} {f.title}")
    lines.append("")

    loc = f"`{f.file_path}:{f.line_start}`"
    if f.line_end and f.line_end != f.line_start:
        loc = f"`{f.file_path}:{f.line_start}-{f.line_end}`"

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Severity** | {icon} {f.severity.value} |")
    lines.append(f"| **Confidence** | {f.confidence.value} |")
    lines.append(f"| **Category** | `{f.category}` |")
    lines.append(f"| **Location** | {loc} |")
    lines.append(f"| **Blocking** | {'Yes' if f.blocking else 'No'} |")
    lines.append(f"| **Source** | {', '.join(f.source_tools)} |")
    if f.rule_id:
        lines.append(f"| **Rule** | `{f.rule_id}` |")
    lines.append(f"| **Disposition** | {f.disposition.value} |")
    lines.append("")

    if f.evidence:
        lines.append("**Evidence:**")
        lines.append("")
        for ev in f.evidence:
            lines.append(f"- {ev}")
        lines.append("")

    lines.append("**Impact:**")
    lines.append("")
    lines.append(f"> {f.impact}")
    lines.append("")

    lines.append("**Fix Recommendation:**")
    lines.append("")
    lines.append(f"> {f.fix_recommendation}")
    lines.append("")

    if f.test_recommendation:
        lines.append("**Test Recommendation:**")
        lines.append("")
        lines.append(f"> {f.test_recommendation}")
        lines.append("")

    return "\n".join(lines)


def format_markdown_report(result: AnalysisResult) -> str:
    """Render a full detailed Markdown report from an AnalysisResult."""
    d = result.decision
    s = result.synthesis
    m = result.metrics
    cls = result.classification
    findings = result.findings

    lines: list[str] = []

    lines.append(f"# Code Review Report — `{d.verdict.value.upper()}`")
    lines.append("")
    lines.append(f"_Generated at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}_")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Verdict** | `{d.verdict.value}` |")
    lines.append(f"| **Confidence** | {d.confidence} |")
    lines.append(f"| **Overall Risk** | {s.overall_risk} |")
    lines.append(f"| **Total Findings** | {len(findings)} |")
    lines.append(f"| **Blocking** | {len(d.blocking_findings)} |")
    lines.append(f"| **Advisory** | {len(d.advisory_findings)} |")
    lines.append(f"| **LLM Model** | {s.model_used} |")
    lines.append(f"| **Degraded Mode** | {'Yes' if s.is_degraded else 'No'} |")
    lines.append("")
    lines.append(d.summary)
    lines.append("")

    lines.append("## Classification")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Change Type** | {cls.change_type} |")
    lines.append(f"| **Domains** | {', '.join(cls.domains)} |")
    lines.append(f"| **Risk Level** | {cls.risk_level} |")
    lines.append(f"| **Profiles** | {', '.join(cls.profiles)} |")
    lines.append("")

    counts = _severity_counts(findings)
    lines.append("## Findings Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in FindingSeverity:
        if counts[sev] > 0:
            lines.append(f"| {_severity_icon(sev)} {sev.value} | {counts[sev]} |")
    lines.append("")

    if not findings:
        lines.append("_No findings._")
        lines.append("")

    if d.blocking_findings:
        lines.append("### Blocking Findings")
        lines.append("")
        for bf in d.blocking_findings:
            lines.append(f"- ❌ {bf}")
        lines.append("")

    if d.escalation_reasons:
        lines.append("### Escalation Reasons")
        lines.append("")
        for er in d.escalation_reasons:
            lines.append(f"- ⚠️ {er}")
        lines.append("")

    if d.missing_evidence:
        lines.append("### Missing Evidence")
        lines.append("")
        for me in d.missing_evidence:
            lines.append(f"- ❓ {me}")
        lines.append("")

    if findings:
        lines.append("## Detailed Findings")
        lines.append("")
        for idx, f in enumerate(findings, 1):
            lines.append(_format_finding(idx, f))

    lines.append("## Collector Results")
    lines.append("")
    lines.append("| Collector | Status | Findings | Duration | Error |")
    lines.append("|-----------|--------|----------|----------|-------|")
    for cr in result.collector_results:
        dur = f"{cr.duration_ms}ms" if cr.duration_ms else "—"
        err = cr.error or "—"
        lines.append(
            f"| {cr.collector_name} | {cr.status} | {len(cr.raw_findings)} | {dur} | {err} |"
        )
    lines.append("")

    lines.append("## Performance Metrics")
    lines.append("")
    lines.append("| Stage | Duration |")
    lines.append("|-------|----------|")
    lines.append(f"| Classification | {m.classification_ms}ms |")
    lines.append(f"| Collection | {m.collection_ms}ms |")
    lines.append(f"| Normalization | {m.normalization_ms}ms |")
    lines.append(f"| Reasoning | {m.reasoning_ms}ms |")
    lines.append(f"| Gate | {m.gate_ms}ms |")
    lines.append(f"| Publishing | {m.publishing_ms}ms |")
    lines.append(f"| **Total** | **{m.total_ms}ms** |")
    lines.append("")
    lines.append(f"LLM cost: ${s.cost_cents / 100:.4f}")
    lines.append("")

    lines.append("---")
    lines.append(f"_Run ID: {m.run_id} · Verdict: {m.verdict}_")
    lines.append("")

    return "\n".join(lines)
