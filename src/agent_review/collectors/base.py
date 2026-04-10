from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from agent_review.scm.github_client import GitHubClient

CollectorStatus = Literal["success", "failure", "timeout", "skipped"]


@dataclass(slots=True)
class CollectorContext:
    repo: str
    pr_number: int
    head_sha: str
    base_sha: str
    changed_files: list[str]
    github_client: GitHubClient


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
