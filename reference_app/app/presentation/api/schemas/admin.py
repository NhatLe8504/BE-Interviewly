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
    is_onboarded: bool = False
    onboarding: dict | None = None


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
    bank_code: str | None = None
    account_number: str | None = None
    sender_bank: str | None = None
    sender_account: str | None = None


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


class SubscriptionPlanAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    plan_name: str
    price: float
    billing_cycle: str
    feature_limits: dict = Field(default_factory=dict)
    is_active: bool
    created_at: datetime | None = None
    subscribers_count: int = 0


class SubscriptionPlanCreateIn(BaseModel):
    plan_name: str = Field(..., min_length=2, max_length=100)
    price: float = Field(0.0, ge=0)
    billing_cycle: str = Field("monthly", pattern="^(free|weekly|monthly|quarterly|yearly)$")
    feature_limits: dict = Field(default_factory=dict)
    is_active: bool = True


class SubscriptionPlanUpdateIn(BaseModel):
    plan_name: str | None = None
    price: float | None = None
    billing_cycle: str | None = Field(None, pattern="^(free|weekly|monthly|quarterly|yearly)$")
    feature_limits: dict | None = None
    is_active: bool | None = None


class UserSubscriptionAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_subscription_id: int
    user_id: int
    user_email: str | None = None
    user_name: str | None = None
    plan_id: int
    plan_name: str | None = None
    status: str
    auto_renew: bool
    start_date: datetime
    end_date: datetime | None = None
    created_at: datetime | None = None


class UserSubscriptionUpdateIn(BaseModel):
    status: str | None = Field(None, pattern="^(active|expired|cancelled|past_due)$")
    auto_renew: bool | None = None
    end_date: datetime | None = None


class UserSubscriptionPageOut(BaseModel):
    items: list[UserSubscriptionAdminOut]
    total: int
    limit: int
    offset: int


class SystemSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ai_model: str
    ai_temperature: float
    ai_max_tokens: int
    ai_interviewer_persona: str
    tts_provider: str
    tts_default_voice: str
    stt_provider: str
    audio_retention_hours: int
    max_upload_size_mb: int
    smtp_host: str
    smtp_port: int
    smtp_sender_name: str
    smtp_sender_email: str
    maintenance_mode: bool
    updated_at: datetime | None = None


class SystemSettingsUpdateIn(BaseModel):
    ai_model: str | None = None
    ai_temperature: float | None = None
    ai_max_tokens: int | None = None
    ai_interviewer_persona: str | None = None
    tts_provider: str | None = None
    tts_default_voice: str | None = None
    stt_provider: str | None = None
    audio_retention_hours: int | None = None
    max_upload_size_mb: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_sender_name: str | None = None
    smtp_sender_email: str | None = None
    maintenance_mode: bool | None = None


class SystemHealthOut(BaseModel):
    database_connected: bool
    redis_connected: bool
    audio_storage_size_mb: float
    server_time: datetime
    active_connections: int
    version: str


