from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    email: str
    phone: str | None = None
    role: str
    preferred_language: str
    status: str
    experience_level: str | None = None
    target_domain_id: int | None = None
    target_domain_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=150)
    phone: str | None = Field(None, max_length=20)
    preferred_language: str | None = Field(None, pattern="^(vi|en)$")
    experience_level: str | None = Field(
        None,
        pattern="^(intern|fresher|junior|middle|senior|lead)$",
    )
    target_domain_id: int | None = None
    bio: str | None = Field(None, max_length=5000)
    avatar_url: str | None = Field(None, max_length=500)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class MessageOut(BaseModel):
    message: str
