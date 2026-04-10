from typing import Literal

from pydantic import BaseModel, Field


class CollectorContext(BaseModel):
    repo: str
    pr_number: int
    head_sha: str
    base_sha: str
    changed_files: list[str]


class CollectorResult(BaseModel):
    collector_name: str
    status: Literal["success", "failure", "timeout", "skipped"]
    raw_findings: list[dict[str, object]]
    duration_ms: int
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
