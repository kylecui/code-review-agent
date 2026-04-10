from __future__ import annotations

from typing import TYPE_CHECKING, cast

from agent_review.collectors.base import CollectorContext
from agent_review.config import Settings
from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.reasoning.llm_client import BudgetExceededError, LLMResponse
from agent_review.reasoning.prompt_manager import PromptManager
from agent_review.reasoning.synthesizer import Synthesizer
from agent_review.schemas.finding import FindingCreate

if TYPE_CHECKING:
    from agent_review.reasoning.llm_client import LLMClient
    from agent_review.scm.github_client import GitHubClient


class FakeLLMClient:
    def __init__(self, content: str, raise_budget: bool = False):
        self.content = content
        self.raise_budget = raise_budget

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        _ = model
        _ = messages
        _ = temperature
        _ = max_tokens
        if self.raise_budget:
            raise BudgetExceededError("budget")
        return LLMResponse(
            content=self.content,
            model="gpt-test",
            usage_prompt_tokens=10,
            usage_completion_tokens=20,
            cost_cents=1.0,
            latency_ms=5,
        )


def _context(changed_files: list[str] | None = None) -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        pr_number=1,
        head_sha="a" * 40,
        base_sha="b" * 40,
        changed_files=changed_files or ["src/a.py"],
        github_client=cast("GitHubClient", object()),
    )


def _finding(
    index: int, file_path: str = "src/a.py", severity: FindingSeverity = FindingSeverity.MEDIUM
) -> FindingCreate:
    return FindingCreate(
        finding_id=f"f-{index}",
        category="quality.issue",
        severity=severity,
        confidence=FindingConfidence.MEDIUM,
        blocking=severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH},
        file_path=file_path,
        line_start=1,
        source_tools=["tool"],
        title=f"title-{index}",
        evidence=["e"],
        impact="impact",
        fix_recommendation="fix",
        fingerprint=f"fp-{index}",
    )


def _llm_json(finding_id: str = "f-0") -> str:
    return (
        "{"
        '"prioritized_findings":[{"finding_id":"'
        + finding_id
        + '","priority":2,"explanation":"x","suggested_fix":"y","is_false_positive":false}],'
        '"summary":"ok","overall_risk":"medium"'
        "}"
    )


async def test_small_tier_single_call() -> None:
    synth = Synthesizer(
        llm_client=cast("LLMClient", FakeLLMClient(_llm_json())),
        prompt_manager=PromptManager(),
        settings=Settings(),
    )
    result = await synth.synthesize([_finding(0)], _context())

    assert result.is_degraded is False
    assert result.model_used == "gpt-test"
    assert result.prioritized_findings[0].finding_id == "f-0"


async def test_medium_tier_chunks_by_file_and_merges() -> None:
    synth = Synthesizer(
        llm_client=cast("LLMClient", FakeLLMClient(_llm_json("f-1"))),
        prompt_manager=PromptManager(),
        settings=Settings(),
    )
    findings = [_finding(i, file_path=f"src/{i}.py") for i in range(600)]
    result = await synth.synthesize(
        findings, _context(changed_files=[f.file_path for f in findings])
    )

    assert result.is_degraded is False
    assert len(result.prioritized_findings) == 600


async def test_large_tier_falls_back_to_degraded() -> None:
    synth = Synthesizer(
        llm_client=cast("LLMClient", FakeLLMClient(_llm_json())),
        prompt_manager=PromptManager(),
        settings=Settings(),
    )
    findings = [_finding(i) for i in range(2001)]
    result = await synth.synthesize(findings, _context())

    assert result.is_degraded is True
    assert result.model_used == "deterministic"


async def test_json_parse_failure_falls_back_to_degraded() -> None:
    synth = Synthesizer(
        llm_client=cast("LLMClient", FakeLLMClient("not-json")),
        prompt_manager=PromptManager(),
        settings=Settings(),
    )
    result = await synth.synthesize([_finding(0)], _context())
    assert result.is_degraded is True


async def test_budget_exceeded_falls_back_to_degraded() -> None:
    synth = Synthesizer(
        llm_client=cast("LLMClient", FakeLLMClient(_llm_json(), raise_budget=True)),
        prompt_manager=PromptManager(),
        settings=Settings(),
    )
    result = await synth.synthesize([_finding(0)], _context())
    assert result.is_degraded is True
