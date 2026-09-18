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


class UserAdminCreateIn(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=100)
    phone: str | None = Field(None, max_length=20)
    role: str = Field("candidate", pattern="^(candidate|admin)$")
    status: str = Field("active", pattern="^(active|suspended|deleted)$")
    preferred_language: str = Field("vi", pattern="^(vi|en)$")


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


class PaymentAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    user_subscription_id: int
    payment_gateway: str
    gateway_transaction_id: str
    amount: float
    currency: str
    status: str
    paid_at: datetime | None = None
    created_at: datetime | None = None
    user_id: int | None = None
    user_email: str | None = None
    user_name: str | None = None
    plan_name: str | None = None


class PaymentListPageOut(BaseModel):
    items: list[PaymentAdminOut]
    total: int
    limit: int
    offset: int


class PaymentStatusUpdateIn(BaseModel):
    status: str = Field(..., pattern="^(pending|success|failed|refunded)$")


class XGateSyncOut(BaseModel):
    success: bool
    scanned_xgate_count: int
    matched_count: int
    new_confirmed_count: int
    message: str
