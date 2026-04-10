from __future__ import annotations

from typing import TYPE_CHECKING

from agent_review.gate.policy_loader import PolicyLoader
from agent_review.models.enums import FailureMode

if TYPE_CHECKING:
    from pathlib import Path


def test_loads_default_policy_yaml(tmp_path: Path) -> None:
    policy_file = tmp_path / "default.policy.yaml"
    policy_file.write_text(
        """
version: 1
collectors:
  semgrep:
    failure_mode: required
""".strip(),
        encoding="utf-8",
    )

    loader = PolicyLoader(policy_dir=tmp_path)
    policy = loader.load()

    assert policy.version == 1
    assert "semgrep" in policy.collectors
    assert policy.collectors["semgrep"].failure_mode == FailureMode.REQUIRED


def test_loads_repo_specific_policy_before_default(tmp_path: Path) -> None:
    (tmp_path / "default.policy.yaml").write_text("version: 1", encoding="utf-8")
    repo_policy = tmp_path / "octo" / "hello.yaml"
    repo_policy.parent.mkdir(parents=True)
    repo_policy.write_text(
        """
version: 2
exceptions:
  emergency_bypass_labels:
    - hotfix
""".strip(),
        encoding="utf-8",
    )

    loader = PolicyLoader(policy_dir=tmp_path)
    policy = loader.load(repo="octo/hello")

    assert policy.version == 2
    assert policy.exceptions.emergency_bypass_labels == ["hotfix"]


def test_falls_back_to_default_config_when_files_missing(tmp_path: Path) -> None:
    loader = PolicyLoader(policy_dir=tmp_path)

    policy = loader.load(repo="missing/repo")

    assert policy.model_dump() == {
        "version": 1,
        "collectors": {},
        "profiles": {},
        "limits": {
            "max_inline_comments": 25,
            "max_summary_findings": 10,
            "max_diff_lines": 10000,
        },
        "exceptions": {"emergency_bypass_labels": []},
    }


def test_malformed_yaml_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / "default.policy.yaml").write_text("version: [", encoding="utf-8")

    loader = PolicyLoader(policy_dir=tmp_path)
    policy = loader.load()

    assert policy.version == 1
    assert policy.collectors == {}


def test_empty_yaml_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / "default.policy.yaml").write_text("", encoding="utf-8")

    loader = PolicyLoader(policy_dir=tmp_path)
    policy = loader.load()

    assert policy.version == 1
    assert policy.profiles == {}
