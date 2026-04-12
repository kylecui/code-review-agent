from pathlib import Path
from typing import ClassVar, Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="AGENT_REVIEW_", env_file=".env"
    )

    database_url: str = "sqlite+aiosqlite:///./dev.db"

    github_app_id: int = 0
    github_private_key: SecretStr = SecretStr("")
    github_webhook_secret: SecretStr = SecretStr("")

    llm_classify_model: str = "gpt-4o-mini"
    llm_synthesize_model: str = "gpt-4o"
    llm_fallback_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 4096
    llm_temperature: float = 1.0
    llm_cost_budget_per_run_cents: int = 50

    sonar_host_url: str | None = None
    sonar_token: SecretStr | None = None
    semgrep_app_token: SecretStr | None = None
    semgrep_mode: Literal["app", "cli", "disabled"] = "app"
    semgrep_rules_path: str = "/opt/semgrep-rules"
    semgrep_severity_filter: list[str] = ["ERROR", "WARNING"]

    max_inline_comments: int = 25
    max_diff_lines: int = 10000

    policy_dir: Path = Path("./policies")
    prompts_dir: Path = Path("./prompts")

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
