from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_review.config import Settings


def test_settings_defaults_load() -> None:
    settings = Settings()

    assert settings.database_url == "sqlite+aiosqlite:///./dev.db"
    assert settings.github_app_id == 0
    assert settings.github_private_key.get_secret_value() == ""
    assert settings.github_webhook_secret.get_secret_value() == ""
    assert settings.llm_classify_model == "gpt-4o-mini"
    assert settings.llm_synthesize_model == "gpt-4o"
    assert settings.llm_fallback_model == "gpt-4o-mini"
    assert settings.llm_max_tokens == 4096
    assert settings.llm_cost_budget_per_run_cents == 50
    assert settings.sonar_host_url is None
    assert settings.sonar_token is None
    assert settings.semgrep_app_token is None
    assert settings.semgrep_mode == "app"
    assert settings.max_inline_comments == 25
    assert settings.max_diff_lines == 10000
    assert settings.policy_dir == Path("./policies")
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_REVIEW_DATABASE_URL", "sqlite+aiosqlite:///./override.db")
    monkeypatch.setenv("AGENT_REVIEW_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("AGENT_REVIEW_SEMGREP_MODE", "disabled")

    settings = Settings()

    assert settings.database_url == "sqlite+aiosqlite:///./override.db"
    assert settings.llm_max_tokens == 2048
    assert settings.semgrep_mode == "disabled"


def test_settings_validation_edge_cases() -> None:
    with pytest.raises(ValidationError):
        _ = Settings.model_validate({"github_app_id": "not-an-int"})

    with pytest.raises(ValidationError):
        _ = Settings.model_validate({"semgrep_mode": "invalid-mode"})

    with pytest.raises(ValidationError):
        _ = Settings.model_validate({"log_format": "plain"})
