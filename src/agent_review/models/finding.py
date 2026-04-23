from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base
from .enums import FindingConfidence, FindingDisposition, FindingSeverity

_UUID_TYPE = uuid.UUID
_DATETIME_TYPE = dt.datetime


class Finding(Base):
    __tablename__: str = "findings"

    id: Mapped[_UUID_TYPE] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    review_run_id: Mapped[_UUID_TYPE] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("review_runs.id"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity), nullable=False)
    confidence: Mapped[FindingConfidence] = mapped_column(Enum(FindingConfidence), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    impact: Mapped[str] = mapped_column(String, nullable=False)
    fix_recommendation: Mapped[str] = mapped_column(String, nullable=False)
    test_recommendation: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    fingerprint_v2: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    engine_tier: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    disposition: Mapped[FindingDisposition] = mapped_column(
        Enum(FindingDisposition),
        nullable=False,
        default=FindingDisposition.NEW,
    )
    created_at: Mapped[_DATETIME_TYPE] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    review_run: Mapped[ReviewRun] = relationship(back_populates="findings")


if TYPE_CHECKING:

    class ReviewRun: ...
