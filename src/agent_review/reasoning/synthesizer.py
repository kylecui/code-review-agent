from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING

from agent_review.reasoning.degraded import DegradedSynthesizer, PrioritizedFinding, SynthesisResult
from agent_review.reasoning.llm_client import BudgetExceededError, LLMClient

if TYPE_CHECKING:
    from agent_review.collectors.base import CollectorContext
    from agent_review.config import Settings
    from agent_review.reasoning.prompt_manager import PromptManager
    from agent_review.schemas.finding import FindingCreate


class Synthesizer:
    def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager, settings: Settings):
        self._llm_client = llm_client
        self._prompt_manager = prompt_manager
        self._settings = settings
        self._degraded = DegradedSynthesizer()

    async def synthesize(
        self,
        findings: list[FindingCreate],
        context: CollectorContext,
    ) -> SynthesisResult:
        total = len(findings)
        if total > 2000:
            return self._degraded.synthesize(findings)

        if total < 500:
            result = await self._synthesize_single_chunk(findings=findings, context=context)
            if result is not None:
                return result
            return self._degraded.synthesize(findings)

        chunked_findings = self._chunk_by_file(findings)
        merged_prioritized: list[PrioritizedFinding] = []
        merged_summary_parts: list[str] = []
        merged_risk = "low"
        merged_model = self._settings.llm_synthesize_model
        merged_cost = 0.0

        for chunk in chunked_findings:
            partial = await self._synthesize_single_chunk(findings=chunk, context=context)
            if partial is None:
                return self._degraded.synthesize(findings)
            merged_prioritized.extend(partial.prioritized_findings)
            merged_summary_parts.append(partial.summary)
            merged_risk = self._higher_risk(merged_risk, partial.overall_risk)
            merged_model = partial.model_used
            merged_cost += partial.cost_cents

        merged_prioritized.sort(key=lambda item: item.priority)
        return SynthesisResult(
            prioritized_findings=merged_prioritized,
            summary="\n".join(part for part in merged_summary_parts if part),
            overall_risk=merged_risk,
            model_used=merged_model,
            cost_cents=merged_cost,
            is_degraded=False,
        )

    async def _synthesize_single_chunk(
        self, findings: list[FindingCreate], context: CollectorContext
    ) -> SynthesisResult | None:
        prompt = self._prompt_manager.render(
            "synthesize.j2",
            repo=context.repo,
            pr_number=context.pr_number,
            changed_files=context.changed_files,
            findings=[finding.model_dump(mode="json") for finding in findings],
        )
        messages = [
            {"role": "system", "content": "You are a precise code review synthesizer."},
            {"role": "user", "content": prompt},
        ]

        try:
            llm_response = await self._llm_client.complete(
                model=self._settings.llm_synthesize_model,
                messages=messages,
                temperature=0.0,
                max_tokens=self._settings.llm_max_tokens,
            )
        except BudgetExceededError:
            return None
        except Exception:
            return None

        parsed = self._parse_json_response(llm_response.content)
        if parsed is None:
            return None

        prioritized_findings = self._parse_prioritized_findings(parsed)
        summary = str(parsed.get("summary", ""))
        overall_risk = str(parsed.get("overall_risk", "medium"))

        return SynthesisResult(
            prioritized_findings=prioritized_findings,
            summary=summary,
            overall_risk=overall_risk,
            model_used=llm_response.model,
            cost_cents=llm_response.cost_cents,
            is_degraded=False,
        )

    @staticmethod
    def _chunk_by_file(findings: list[FindingCreate]) -> list[list[FindingCreate]]:
        grouped: dict[str, list[FindingCreate]] = defaultdict(list)
        for finding in findings:
            grouped[finding.file_path].append(finding)
        return list(grouped.values())

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, object] | None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _parse_prioritized_findings(payload: dict[str, object]) -> list[PrioritizedFinding]:
        entries = payload.get("prioritized_findings")
        if not isinstance(entries, list):
            return []

        parsed: list[PrioritizedFinding] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            priority = entry.get("priority", 3)
            is_false_positive = entry.get("is_false_positive", False)

            parsed.append(
                PrioritizedFinding(
                    finding_id=str(entry.get("finding_id", "")),
                    priority=priority if isinstance(priority, int) else 3,
                    explanation=str(entry.get("explanation", "")),
                    suggested_fix=str(entry.get("suggested_fix", "")),
                    is_false_positive=bool(is_false_positive),
                )
            )

        parsed.sort(key=lambda item: item.priority)
        return parsed

    @staticmethod
    def _higher_risk(current: str, candidate: str) -> str:
        rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        current_rank = rank.get(current, 1)
        candidate_rank = rank.get(candidate, 1)
        return candidate if candidate_rank > current_rank else current
