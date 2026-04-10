from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_review.reasoning.degraded import SynthesisResult


def build_decision_summary(
    synthesis: SynthesisResult,
    required_failed_collectors: list[str],
    degraded_collectors: list[str],
) -> str:
    parts = [synthesis.summary]
    if synthesis.is_degraded:
        parts.append("Synthesis ran in degraded mode.")
    if required_failed_collectors:
        parts.append(
            "Required collectors failed: " + ", ".join(sorted(required_failed_collectors)) + "."
        )
    if degraded_collectors:
        parts.append("Collector evidence degraded: " + ", ".join(sorted(degraded_collectors)) + ".")
    return " ".join(part for part in parts if part)
