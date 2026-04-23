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
    secret_key: SecretStr = SecretStr("change-me-in-production")
    access_token_expire_minutes: int = 60

    github_oauth_client_id: str = ""
    github_oauth_client_secret: SecretStr = SecretStr("")
    oauth_redirect_uri: str = ""

    llm_classify_model: str = "gpt-4o-mini"
    llm_synthesize_model: str = "gpt-4o"
    llm_fallback_model: str = "gpt-4o-mini"
    llm_openai_api_key: SecretStr = SecretStr("")
    llm_gemini_api_key: SecretStr = SecretStr("")
    llm_github_api_key: SecretStr = SecretStr("")
    llm_anthropic_api_key: SecretStr = SecretStr("")
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
    frontend_dir: Path = Path("./static")
    upload_dir: Path = Path("/tmp/agent_review_uploads")
    upload_max_bytes: int = 200 * 1024 * 1024  # 200 MB

    cors_origins: list[str] = []

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
