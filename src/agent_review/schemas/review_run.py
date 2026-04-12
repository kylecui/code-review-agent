import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from agent_review.models.enums import ReviewState, RunKind, TriggerEvent


class ReviewRunCreate(BaseModel):
    repo: str
    run_kind: RunKind = RunKind.PR
    pr_number: int | None = None
    head_sha: str = Field(min_length=40, max_length=40)
    base_sha: str | None = Field(default=None, min_length=40, max_length=40)
    installation_id: int | None = None
    trigger_event: TriggerEvent | None = None
    delivery_id: str | None = None


class ReviewRunRead(BaseModel):
    id: uuid.UUID
    repo: str
    run_kind: RunKind
    pr_number: int | None
    head_sha: str
    base_sha: str | None
    installation_id: int | None
    attempt: int
    state: ReviewState
    superseded_by: uuid.UUID | None
    trigger_event: TriggerEvent | None
    delivery_id: str | None
    classification: dict[str, object] | None
    decision: dict[str, object] | None
    metrics: dict[str, object] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class ReviewRunUpdate(BaseModel):
    state: ReviewState | None = None
    classification: dict[str, object] | None = None
    decision: dict[str, object] | None = None
    metrics: dict[str, object] | None = None
    error: str | None = None


class ScanRequest(BaseModel):
    """Request body for baseline repository scan (POST /api/scan)."""

    repo: str = Field(description="Repository in owner/name format")
    installation_id: int | None = Field(
        default=None, description="GitHub App installation ID; auto-discovered when omitted"
    )
    branch: str | None = Field(
        default=None, description="Branch to scan; defaults to the repo default branch"
    )
    ref: str | None = Field(
        default=None,
        min_length=40,
        max_length=40,
        description="Exact commit SHA to scan; takes precedence over branch",
    )
    path: str | None = Field(
        default=None,
        description="Local filesystem path to scan (standalone mode, no GitHub required)",
    )
