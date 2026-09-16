from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    email: str
    phone: str | None = None
    role: str
    status: str
    preferred_language: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserStatusUpdateIn(BaseModel):
    status: str = Field(..., pattern="^(active|suspended|deleted)$")


class UserRoleUpdateIn(BaseModel):
    role: str = Field(..., pattern="^(candidate|admin)$")


class UserListPageOut(BaseModel):
    items: list[UserAdminOut]
    total: int
    limit: int
    offset: int


class SystemStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_users: int
    active_users: int
    total_sessions: int
    completed_sessions: int
    total_questions: int
    total_revenue: float


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    user_id: int | None = None
    table_name: str
    record_id: int | None = None
    action: str
    old_value: dict | None = None
    new_value: dict | None = None
    created_at: datetime | None = None


class AuditLogPageOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


class ModerationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    admin_id: int
    target_type: str
    target_id: int | None = None
    action: str
    reason: str | None = None
    created_at: datetime | None = None


class ModerationCreateIn(BaseModel):
    target_type: str = Field(..., pattern="^(question|answer|user|session|comment)$")
    action: str = Field(..., pattern="^(flag|approve|reject|remove|warn)$")
    target_id: int | None = None
    reason: str | None = Field(None, max_length=1000)


class ModerationPageOut(BaseModel):
    items: list[ModerationItemOut]
    total: int
    limit: int
    offset: int
