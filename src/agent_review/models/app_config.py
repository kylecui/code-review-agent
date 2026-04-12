from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base

_UUID_TYPE = uuid.UUID
_DATETIME_TYPE = dt.datetime


class AppConfig(Base):
    __tablename__: str = "app_config"

    id: Mapped[_UUID_TYPE] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialized
    updated_at: Mapped[_DATETIME_TYPE] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[_UUID_TYPE | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
