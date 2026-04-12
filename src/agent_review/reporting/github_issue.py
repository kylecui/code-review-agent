"""Publish baseline scan results as a GitHub Issue."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from agent_review.config import Settings
from agent_review.scm.github_auth import GitHubAppAuth
from agent_review.scm.github_client import GitHubClient

if TYPE_CHECKING:
    from agent_review.pipeline.analysis import AnalysisResult


def _build_issue_body(result: AnalysisResult, repo: str) -> str:
    d = result.decision
    s = result.synthesis
    lines: list[str] = [
        f"## Baseline Scan — `{repo}`",
        "",
    ]
    verdict = f"**Verdict:** `{d.verdict.value}` · **Confidence:** {d.confidence}"
    lines.append(f"{verdict} · **Overall Risk:** {s.overall_risk}")
    lines += [
        "",
        d.summary,
        "",
    ]

    if result.findings:
        lines.append(f"### Findings ({len(result.findings)})")
        lines.append("")
        lines.append("| # | Severity | Category | File | Title |")
        lines.append("|---|----------|----------|------|-------|")
        for i, f in enumerate(result.findings, 1):
            loc = f"{f.file_path}:{f.line_start}"
            lines.append(f"| {i} | {f.severity.value} | {f.category} | `{loc}` | {f.title} |")
        lines.append("")
    else:
        lines.append("_No findings._")
        lines.append("")

    if d.blocking_findings:
        lines.append("### Blocking")
        lines.append("")
        for bf in d.blocking_findings:
            lines.append(f"- {bf}")
        lines.append("")

    if d.escalation_reasons:
        lines.append("### Escalation Reasons")
        lines.append("")
        for er in d.escalation_reasons:
            lines.append(f"- {er}")
        lines.append("")

    collectors = result.collector_results
    lines.append("### Collectors")
    lines.append("")
    lines.append("| Collector | Status | Findings | Duration |")
    lines.append("|-----------|--------|----------|----------|")
    for cr in collectors:
        dur = f"{cr.duration_ms}ms" if cr.duration_ms else "—"
        lines.append(f"| {cr.collector_name} | {cr.status} | {len(cr.raw_findings)} | {dur} |")
    lines.append("")

    lines.append("---")
    lines.append(
        f"_Model: {s.model_used} · Degraded: {s.is_degraded} · Cost: ${s.cost_cents / 100:.4f}_"
    )

    return "\n".join(lines)


async def publish_github_issue(
    result: AnalysisResult,
    *,
    repo: str,
    installation_id: int,
    config_path: str | None = None,
) -> str:
    settings = (
        Settings(_env_file=config_path) if config_path else Settings()  # type: ignore[call-arg]
    )

    auth = GitHubAppAuth(
        settings.github_app_id,
        settings.github_private_key.get_secret_value(),
    )

    title = f"Baseline Scan: {result.decision.verdict.value} — {repo}"
    body = _build_issue_body(result, repo)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        github = GitHubClient(http_client, auth, installation_id)
        issue = await github.create_issue(
            repo, title, body, labels=["code-review", "baseline-scan"]
        )

    return str(issue.get("html_url", ""))
