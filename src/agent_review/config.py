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

    # --- v0.2.0: New collector settings (all disabled by default) ---

    # L1 - Gitleaks (secret scanning)
    gitleaks_mode: Literal["cli", "disabled"] = "disabled"
    gitleaks_config_path: str = ""

    # L2 - SpotBugs (Java bytecode analysis)
    spotbugs_mode: Literal["cli", "disabled"] = "disabled"
    spotbugs_path: str = "/opt/spotbugs/bin/spotbugs"
    spotbugs_findsecbugs_plugin: str = "/opt/findsecbugs-plugin.jar"
    spotbugs_effort: Literal["min", "default", "max"] = "max"

    # L2 - golangci-lint (Go)
    golangci_lint_mode: Literal["cli", "disabled"] = "disabled"
    golangci_lint_config_path: str = ""
    golangci_lint_timeout: int = 300

    # L2 - Cppcheck (C/C++)
    cppcheck_mode: Literal["cli", "disabled"] = "disabled"
    cppcheck_enable: str = "all"
    cppcheck_suppressions: list[str] = ["missingIncludeSystem"]

    # L2 - Clang-Tidy (C/C++)
    clang_tidy_mode: Literal["cli", "disabled"] = "disabled"
    clang_tidy_checks: str = "clang-analyzer-*,cert-*,bugprone-*"

    # L2 - ESLint Security (JS/TS)
    eslint_security_mode: Literal["cli", "disabled"] = "disabled"
    eslint_security_config_path: str = "/opt/eslint-security.config.mjs"

    # L2 - Roslyn (C#)
    roslyn_mode: Literal["cli", "disabled"] = "disabled"
    roslyn_severity: str = "info"

    # L2 - Luacheck (Lua)
    luacheck_mode: Literal["cli", "disabled"] = "disabled"
    luacheck_config_path: str = ""

    # L3 - CodeQL (graph-based taint analysis)
    codeql_mode: Literal["cli", "disabled"] = "disabled"
    codeql_path: str = "/opt/codeql/codeql"
    codeql_threads: int = 0
    codeql_ram: int = 8192
    codeql_timeout: int = 1800
