from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base
from .enums import ReviewState, RunKind, TriggerEvent

_UUID_TYPE = uuid.UUID
_DATETIME_TYPE = dt.datetime


class InvalidTransitionError(ValueError):
    pass


InvalidTransition = InvalidTransitionError


class ReviewRun(Base):
    __tablename__: str = "review_runs"
    __table_args__: tuple[Index, ...] = (
        Index("ix_review_runs_repo_pr_number", "repo", "pr_number"),
    )

    VALID_TRANSITIONS: ClassVar[dict[ReviewState, set[ReviewState]]] = {
        ReviewState.PENDING: {ReviewState.CLASSIFYING, ReviewState.FAILED, ReviewState.SUPERSEDED},
        ReviewState.CLASSIFYING: {
            ReviewState.COLLECTING,
            ReviewState.FAILED,
            ReviewState.SUPERSEDED,
        },
        ReviewState.COLLECTING: {
            ReviewState.NORMALIZING,
            ReviewState.FAILED,
            ReviewState.SUPERSEDED,
        },
        ReviewState.NORMALIZING: {
            ReviewState.REASONING,
            ReviewState.FAILED,
            ReviewState.SUPERSEDED,
        },
        ReviewState.REASONING: {ReviewState.DECIDING, ReviewState.FAILED, ReviewState.SUPERSEDED},
        ReviewState.DECIDING: {ReviewState.PUBLISHING, ReviewState.FAILED, ReviewState.SUPERSEDED},
        ReviewState.PUBLISHING: {ReviewState.COMPLETED, ReviewState.FAILED, ReviewState.SUPERSEDED},
        ReviewState.COMPLETED: set(),
        ReviewState.FAILED: set(),
        ReviewState.SUPERSEDED: set(),
    }

    id: Mapped[_UUID_TYPE] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    repo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_kind: Mapped[RunKind] = mapped_column(
        Enum(RunKind),
        nullable=False,
        default=RunKind.PR,
    )
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    base_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[ReviewState] = mapped_column(
        Enum(ReviewState),
        nullable=False,
        default=ReviewState.PENDING,
        index=True,
    )
    superseded_by: Mapped[_UUID_TYPE | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("review_runs.id"),
        nullable=True,
    )
    trigger_event: Mapped[TriggerEvent | None] = mapped_column(Enum(TriggerEvent), nullable=True)
    delivery_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    classification: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    run_logs: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    detected_languages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    engine_selection: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[_DATETIME_TYPE] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[_DATETIME_TYPE] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[_DATETIME_TYPE | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    findings: Mapped[list[Finding]] = relationship(back_populates="review_run")

    def transition(self, new_state: ReviewState) -> None:
        allowed_states = self.VALID_TRANSITIONS[self.state]
        if new_state not in allowed_states:
            raise InvalidTransition(
                f"Invalid transition from {self.state.value} to {new_state.value}"
            )

        now = dt.datetime.now(dt.UTC)
        self.state = new_state
        self.updated_at = now
        if new_state in {ReviewState.COMPLETED, ReviewState.FAILED, ReviewState.SUPERSEDED}:
            self.completed_at = now

    @property
    def is_terminal(self) -> bool:
        return self.state in {ReviewState.COMPLETED, ReviewState.FAILED, ReviewState.SUPERSEDED}

    @property
    def is_active(self) -> bool:
        return not self.is_terminal


if TYPE_CHECKING:

    class Finding: ...
