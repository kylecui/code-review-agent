from __future__ import annotations

from pathlib import Path

import pytest

from agent_review.reasoning.prompt_manager import PromptManager, TemplateNotFoundError


def test_render_template_success() -> None:
    manager = PromptManager(template_dir=Path("/home/kylecui/code-review-agent/prompts"))

    rendered = manager.render(
        "summarize.j2",
        verdict="warn",
        total_findings=3,
        blocking_findings=1,
        advisory_findings=2,
        top_findings=[
            {
                "severity": "high",
                "title": "Issue",
                "file_path": "src/a.py",
                "line_start": 10,
            }
        ],
    )

    assert "Verdict: warn" in rendered
    assert "Total findings: 3" in rendered


def test_render_sanitizes_very_long_strings() -> None:
    manager = PromptManager(template_dir=Path("/home/kylecui/code-review-agent/prompts"))
    long_text = "x" * 100_100

    rendered = manager.render(
        "summarize.j2",
        verdict=long_text,
        total_findings=0,
        blocking_findings=0,
        advisory_findings=0,
        top_findings=[],
    )

    assert "[TRUNCATED]" in rendered


def test_missing_template_dir_or_template_raises() -> None:
    with pytest.raises(TemplateNotFoundError):
        _ = PromptManager(template_dir=Path("/home/kylecui/code-review-agent/does-not-exist"))

    manager = PromptManager(template_dir=Path("/home/kylecui/code-review-agent/prompts"))
    with pytest.raises(TemplateNotFoundError):
        _ = manager.render("missing.j2", key="value")
