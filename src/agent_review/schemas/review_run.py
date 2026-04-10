import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from agent_review.models.enums import ReviewState, TriggerEvent


class ReviewRunCreate(BaseModel):
    repo: str
    pr_number: int
    head_sha: str = Field(min_length=40, max_length=40)
    base_sha: str = Field(min_length=40, max_length=40)
    installation_id: int
    trigger_event: TriggerEvent
    delivery_id: str


class ReviewRunRead(BaseModel):
    id: uuid.UUID
    repo: str
    pr_number: int
    head_sha: str
    base_sha: str
    installation_id: int
    attempt: int
    state: ReviewState
    superseded_by: uuid.UUID | None
    trigger_event: TriggerEvent
    delivery_id: str
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
