from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import litellm

if TYPE_CHECKING:
    from agent_review.config import Settings


class LLMError(Exception):
    pass


class BudgetExceededError(Exception):
    pass


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    usage_prompt_tokens: int
    usage_completion_tokens: int
    cost_cents: float
    latency_ms: int


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._total_cost_cents: float = 0.0

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        estimated_cost_cents = self._estimate_cost_cents(messages=messages, max_tokens=max_tokens)
        if (
            self._total_cost_cents + estimated_cost_cents
            > self._settings.llm_cost_budget_per_run_cents
        ):
            raise BudgetExceededError("LLM budget exceeded before completion call")

        started = time.perf_counter()
        try:
            response: Any = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise LLMError(f"LLM completion failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_cost = 0.0
        hidden_params = getattr(response, "_hidden_params", None)
        if isinstance(hidden_params, dict):
            hidden_cost = hidden_params.get("response_cost", 0.0)
            if isinstance(hidden_cost, int | float):
                raw_cost = float(hidden_cost)

        cost_cents = raw_cost * 100.0
        if self._total_cost_cents + cost_cents > self._settings.llm_cost_budget_per_run_cents:
            raise BudgetExceededError("LLM budget exceeded after completion call")

        usage_prompt_tokens = 0
        usage_completion_tokens = 0
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", 0)
            if isinstance(prompt_tokens, int):
                usage_prompt_tokens = prompt_tokens
            if isinstance(completion_tokens, int):
                usage_completion_tokens = completion_tokens

        content = ""
        choices = getattr(response, "choices", None)
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            if message is not None:
                maybe_content = getattr(message, "content", "")
                content = str(maybe_content) if maybe_content is not None else ""

        resolved_model = str(getattr(response, "model", model))
        self._total_cost_cents += cost_cents
        return LLMResponse(
            content=content,
            model=resolved_model,
            usage_prompt_tokens=usage_prompt_tokens,
            usage_completion_tokens=usage_completion_tokens,
            cost_cents=cost_cents,
            latency_ms=latency_ms,
        )

    @property
    def total_cost_cents(self) -> float:
        return self._total_cost_cents

    @staticmethod
    def _estimate_cost_cents(messages: list[dict[str, str]], max_tokens: int | None) -> float:
        estimated_prompt_tokens = sum(len(message.get("content", "")) // 4 for message in messages)
        estimated_completion_tokens = max_tokens if max_tokens is not None else 0
        estimated_total_tokens = estimated_prompt_tokens + estimated_completion_tokens
        return float(estimated_total_tokens) * 0.0
