from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_review.config import Settings
from agent_review.reasoning.llm_client import BudgetExceededError, LLMClient, LLMError


def _mock_response(content: str, model: str, cost: float) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        _hidden_params={"response_cost": cost},
    )


async def test_complete_tracks_cost_and_usage() -> None:
    client = LLMClient(Settings(llm_cost_budget_per_run_cents=100))
    mocked = AsyncMock(return_value=_mock_response('{"ok": true}', "gpt-x", 0.05))

    with patch("agent_review.reasoning.llm_client.litellm.acompletion", mocked):
        response = await client.complete(
            model="gpt-x",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.0,
        )

    assert response.content == '{"ok": true}'
    assert response.model == "gpt-x"
    assert response.usage_prompt_tokens == 10
    assert response.usage_completion_tokens == 20
    assert response.cost_cents == 5.0
    assert client.total_cost_cents == 5.0


async def test_complete_raises_budget_exceeded_after_call() -> None:
    client = LLMClient(Settings(llm_cost_budget_per_run_cents=1))
    mocked = AsyncMock(return_value=_mock_response("x", "gpt-x", 0.02))

    with (
        patch("agent_review.reasoning.llm_client.litellm.acompletion", mocked),
        pytest.raises(BudgetExceededError),
    ):
        await client.complete(model="gpt-x", messages=[{"role": "user", "content": "hello"}])


async def test_complete_wraps_litellm_errors() -> None:
    client = LLMClient(Settings())
    mocked = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch("agent_review.reasoning.llm_client.litellm.acompletion", mocked),
        pytest.raises(LLMError),
    ):
        await client.complete(model="gpt-x", messages=[{"role": "user", "content": "hello"}])
