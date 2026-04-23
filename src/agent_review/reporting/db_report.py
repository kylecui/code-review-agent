from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent_review.models.enums import FindingSeverity

_SEVERITY_ICON: dict[str, str] = {
    "critical": "\U0001f534",
    "high": "\U0001f7e0",
    "medium": "\U0001f7e1",
    "low": "\U0001f535",
    "info": "\u26aa",
}


def _icon(severity: str) -> str:
    return _SEVERITY_ICON.get(severity, "\u26aa")


def build_json_report(
    scan: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    decision = scan.get("decision") or {}
    classification = scan.get("classification") or {}
    metrics = scan.get("metrics") or {}

    return {
        "report_generated_at": datetime.now(UTC).isoformat(),
        "scan_id": str(scan.get("id", "")),
        "repo": scan.get("repo", ""),
        "head_sha": scan.get("head_sha", ""),
        "state": scan.get("state", ""),
        "run_kind": scan.get("run_kind", ""),
        "created_at": _isoformat(scan.get("created_at")),
        "completed_at": _isoformat(scan.get("completed_at")),
        "verdict": decision.get("verdict", ""),
        "confidence": decision.get("confidence", ""),
        "summary": decision.get("summary", ""),
        "classification": classification,
        "metrics": {
            "total_ms": metrics.get("total_ms", 0),
            "classification_ms": metrics.get("classification_ms", 0),
            "collection_ms": metrics.get("collection_ms", 0),
            "normalization_ms": metrics.get("normalization_ms", 0),
            "reasoning_ms": metrics.get("reasoning_ms", 0),
            "gate_ms": metrics.get("gate_ms", 0),
            "publishing_ms": metrics.get("publishing_ms", 0),
            "llm_cost_cents": metrics.get("llm_cost_cents", 0),
            "is_degraded": metrics.get("is_degraded", False),
        },
        "blocking_findings": decision.get("blocking_findings", []),
        "advisory_findings": decision.get("advisory_findings", []),
        "escalation_reasons": decision.get("escalation_reasons", []),
        "missing_evidence": decision.get("missing_evidence", []),
        "collector_results": _extract_collector_summary(metrics),
        "findings": [
            {
                "finding_id": f.get("finding_id", ""),
                "category": f.get("category", ""),
                "severity": f.get("severity", ""),
                "confidence": f.get("confidence", ""),
                "blocking": f.get("blocking", False),
                "file_path": f.get("file_path", ""),
                "line_start": f.get("line_start", 0),
                "line_end": f.get("line_end"),
                "source_tools": f.get("source_tools", []),
                "rule_id": f.get("rule_id"),
                "title": f.get("title", ""),
                "impact": f.get("impact", ""),
                "fix_recommendation": f.get("fix_recommendation", ""),
                "test_recommendation": f.get("test_recommendation"),
                "evidence": f.get("evidence", []),
                "fingerprint": f.get("fingerprint", ""),
                "disposition": f.get("disposition", "new"),
            }
            for f in findings
        ],
    }


def build_markdown_report(
    scan: dict[str, Any],
    findings: list[dict[str, Any]],
) -> str:
    decision = scan.get("decision") or {}
    classification = scan.get("classification") or {}
    metrics = scan.get("metrics") or {}

    verdict = decision.get("verdict", "unknown").upper()
    lines: list[str] = []

    lines.append(f"# Code Review Report \u2014 `{verdict}`")
    lines.append("")
    lines.append(f"_Generated at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}_")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Verdict** | `{decision.get('verdict', '')}` |")
    lines.append(f"| **Confidence** | {decision.get('confidence', '')} |")
    lines.append(f"| **Total Findings** | {len(findings)} |")
    lines.append(f"| **Blocking** | {len(decision.get('blocking_findings', []))} |")
    lines.append(f"| **Advisory** | {len(decision.get('advisory_findings', []))} |")
    lines.append(f"| **Degraded Mode** | {'Yes' if metrics.get('is_degraded') else 'No'} |")
    lines.append("")

    summary = decision.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")

    lines.append("## Scan Info")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Scan ID** | `{scan.get('id', '')}` |")
    lines.append(f"| **Repository** | `{scan.get('repo', '')}` |")
    lines.append(f"| **Head SHA** | `{scan.get('head_sha', '')}` |")
    lines.append(f"| **Kind** | {scan.get('run_kind', '')} |")
    lines.append(f"| **Created** | {_isoformat(scan.get('created_at'))} |")
    lines.append(f"| **Completed** | {_isoformat(scan.get('completed_at'))} |")
    lines.append("")

    if classification:
        lines.append("## Classification")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Change Type** | {classification.get('change_type', '')} |")
        domains = classification.get("domains", [])
        lines.append(f"| **Domains** | {', '.join(domains) if domains else ''} |")
        lines.append(f"| **Risk Level** | {classification.get('risk_level', '')} |")
        profiles = classification.get("profiles", [])
        lines.append(f"| **Profiles** | {', '.join(profiles) if profiles else ''} |")
        lines.append("")

    severity_counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    lines.append("## Findings Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in FindingSeverity:
        count = severity_counts.get(sev.value, 0)
        if count > 0:
            lines.append(f"| {_icon(sev.value)} {sev.value} | {count} |")
    lines.append("")

    if not findings:
        lines.append("_No findings._")
        lines.append("")

    blocking = decision.get("blocking_findings", [])
    if blocking:
        lines.append("### Blocking Findings")
        lines.append("")
        for bf in blocking:
            lines.append(f"- \u274c {bf}")
        lines.append("")

    escalation = decision.get("escalation_reasons", [])
    if escalation:
        lines.append("### Escalation Reasons")
        lines.append("")
        for er in escalation:
            lines.append(f"- \u26a0\ufe0f {er}")
        lines.append("")

    missing = decision.get("missing_evidence", [])
    if missing:
        lines.append("### Missing Evidence")
        lines.append("")
        for me in missing:
            lines.append(f"- \u2753 {me}")
        lines.append("")

    if findings:
        lines.append("## Detailed Findings")
        lines.append("")
        for idx, f in enumerate(findings, 1):
            lines.append(_format_finding_md(idx, f))

    collector_summary = _extract_collector_summary(metrics)
    if collector_summary:
        lines.append("## Collector Results")
        lines.append("")
        lines.append("| Collector | Status | Findings | Duration | Error |")
        lines.append("|-----------|--------|----------|----------|-------|")
        for cr in collector_summary:
            dur = f"{cr['duration_ms']}ms" if cr.get("duration_ms") else "\u2014"
            err = cr.get("error") or "\u2014"
            lines.append(
                f"| {cr['name']} | {cr.get('status', '')} | "
                f"{cr.get('finding_count', 0)} | {dur} | {err} |"
            )
        lines.append("")

    lines.append("## Performance Metrics")
    lines.append("")
    lines.append("| Stage | Duration |")
    lines.append("|-------|----------|")
    for stage in (
        "classification",
        "collection",
        "normalization",
        "reasoning",
        "gate",
        "publishing",
    ):
        ms = metrics.get(f"{stage}_ms", 0)
        lines.append(f"| {stage.title()} | {ms}ms |")
    total = metrics.get("total_ms", 0)
    lines.append(f"| **Total** | **{total}ms** |")
    lines.append("")

    cost = metrics.get("llm_cost_cents", 0)
    if cost:
        lines.append(f"LLM cost: ${cost / 100:.4f}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Run ID: {scan.get('id', '')} \u00b7 Verdict: {decision.get('verdict', '')}_")
    lines.append("")
    return "\n".join(lines)


def _isoformat(val: Any) -> str:
    if val is None:
        return "\u2014"
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _extract_collector_summary(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    collector_metrics = metrics.get("collector_metrics", {})
    results: list[dict[str, Any]] = []
    for name, data in collector_metrics.items():
        if not isinstance(data, dict):
            continue
        results.append(
            {
                "name": name,
                "status": data.get("status", ""),
                "duration_ms": data.get("duration_ms", 0),
                "finding_count": data.get("finding_count", 0),
                "error": data.get("error"),
            }
        )
    return results


def _format_finding_md(idx: int, f: dict[str, Any]) -> str:
    sev = f.get("severity", "info")
    icon = _icon(sev)
    title = f.get("title", "Untitled")
    lines: list[str] = []
    lines.append(f"### {idx}. {icon} {title}")
    lines.append("")

    file_path = f.get("file_path", "")
    line_start = f.get("line_start", 0)
    line_end = f.get("line_end")
    loc = f"`{file_path}:{line_start}`"
    if line_end and line_end != line_start:
        loc = f"`{file_path}:{line_start}-{line_end}`"

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Severity** | {icon} {sev} |")
    lines.append(f"| **Confidence** | {f.get('confidence', '')} |")
    lines.append(f"| **Category** | `{f.get('category', '')}` |")
    lines.append(f"| **Location** | {loc} |")
    lines.append(f"| **Blocking** | {'Yes' if f.get('blocking') else 'No'} |")
    source_tools = f.get("source_tools", [])
    lines.append(f"| **Source** | {', '.join(source_tools) if source_tools else ''} |")
    rule_id = f.get("rule_id")
    if rule_id:
        lines.append(f"| **Rule** | `{rule_id}` |")
    disposition = f.get("disposition", "")
    if disposition:
        lines.append(f"| **Disposition** | {disposition} |")
    lines.append("")

    evidence = f.get("evidence", [])
    if evidence:
        lines.append("**Evidence:**")
        lines.append("")
        for ev in evidence:
            lines.append(f"- {ev}")
        lines.append("")

    impact = f.get("impact", "")
    if impact:
        lines.append("**Impact:**")
        lines.append("")
        lines.append(f"> {impact}")
        lines.append("")

    fix = f.get("fix_recommendation", "")
    if fix:
        lines.append("**Fix Recommendation:**")
        lines.append("")
        lines.append(f"> {fix}")
        lines.append("")

    test_rec = f.get("test_recommendation")
    if test_rec:
        lines.append("**Test Recommendation:**")
        lines.append("")
        lines.append(f"> {test_rec}")
        lines.append("")

    return "\n".join(lines)
