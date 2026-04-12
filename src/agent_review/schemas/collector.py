from typing import Literal

from pydantic import BaseModel, Field


class CollectorContext(BaseModel):
    repo: str
    head_sha: str
    changed_files: list[str]
    run_kind: str = "pr"
    pr_number: int | None = None
    base_sha: str | None = None


class CollectorResult(BaseModel):
    collector_name: str
    status: Literal["success", "failure", "timeout", "skipped"]
    raw_findings: list[dict[str, object]]
    duration_ms: int
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
