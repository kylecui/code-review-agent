import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str | None = None


class TokenPayload(BaseModel):
    sub: str
    is_superuser: bool = False
    exp: datetime | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    github_id: int | None
    github_login: str | None
    created_at: datetime
    updated_at: datetime

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str | None = None
    is_superuser: bool = False


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
