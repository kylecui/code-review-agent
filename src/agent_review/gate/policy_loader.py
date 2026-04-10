from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from agent_review.schemas.policy import PolicyConfig

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class PolicyLoader:
    def __init__(self, policy_dir: Path):
        self._policy_dir: Path = policy_dir

    def load(self, repo: str | None = None) -> PolicyConfig:
        policy_path = self._resolve_policy_path(repo)
        if policy_path is None:
            return PolicyConfig()

        try:
            raw_data: object = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse policy YAML at %s: %s", policy_path, exc)
            return PolicyConfig()
        except OSError as exc:
            logger.warning("Failed to read policy file at %s: %s", policy_path, exc)
            return PolicyConfig()

        if raw_data is None:
            return PolicyConfig()

        if not isinstance(raw_data, dict):
            logger.warning("Policy YAML at %s must be a mapping", policy_path)
            return PolicyConfig()

        normalized_data: dict[str, object] = {str(key): value for key, value in raw_data.items()}

        try:
            return PolicyConfig.model_validate(normalized_data)
        except ValidationError as exc:
            logger.warning("Policy validation failed for %s: %s", policy_path, exc)
            return PolicyConfig()

    def _resolve_policy_path(self, repo: str | None) -> Path | None:
        if repo:
            owner, repo_name = self._parse_repo(repo)
            if owner and repo_name:
                repo_path = self._policy_dir / owner / f"{repo_name}.yaml"
                if repo_path.exists():
                    return repo_path

        default_path = self._policy_dir / "default.policy.yaml"
        if default_path.exists():
            return default_path

        return None

    @staticmethod
    def _parse_repo(repo: str) -> tuple[str | None, str | None]:
        parts = repo.split("/", maxsplit=1)
        if len(parts) != 2:
            return None, None

        owner = parts[0].strip()
        repo_name = parts[1].strip()
        if not owner or not repo_name:
            return None, None

        return owner, repo_name
