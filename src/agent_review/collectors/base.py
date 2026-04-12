from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient

CollectorStatus = Literal["success", "failure", "timeout", "skipped"]


@dataclass(slots=True)
class CollectorContext:
    repo: str
    head_sha: str
    changed_files: list[str]
    github_client: GitHubClient | None = None
    run_kind: str = "pr"
    pr_number: int | None = None
    base_sha: str | None = None
    local_path: str | None = None


@dataclass(slots=True)
class CollectorResult:
    collector_name: str
    status: CollectorStatus
    raw_findings: list[dict[str, object]]
    duration_ms: int
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AbstractCollector(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def collect(self, context: CollectorContext) -> CollectorResult:
        raise NotImplementedError
