from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base

_UUID_TYPE = uuid.UUID
_DATETIME_TYPE = dt.datetime


class User(Base):
    __tablename__: str = "users"

    id: Mapped[_UUID_TYPE] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    github_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    github_login: Mapped[str | None] = mapped_column(String, nullable=True)
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
