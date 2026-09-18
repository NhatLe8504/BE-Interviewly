from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import DomainValidationError

VALID_USER_STATUSES = frozenset({"active", "suspended", "deleted"})
VALID_USER_ROLES = frozenset({"candidate", "admin"})
VALID_TARGET_TYPES = frozenset({"question", "answer", "user", "session", "comment"})
VALID_MODERATION_ACTIONS = frozenset({"flag", "approve", "reject", "remove", "warn"})


def validate_user_status(status: str) -> str:
    cleaned = status.strip().lower()
    if cleaned not in VALID_USER_STATUSES:
        allowed = ", ".join(sorted(VALID_USER_STATUSES))
        raise DomainValidationError(f"invalid user status: {status}. Allowed: {allowed}")
    return cleaned


def validate_user_role(role: str) -> str:
    cleaned = role.strip().lower()
    if cleaned not in VALID_USER_ROLES:
        allowed = ", ".join(sorted(VALID_USER_ROLES))
        raise DomainValidationError(f"invalid user role: {role}. Allowed: {allowed}")
    return cleaned


def validate_target_type(target_type: str) -> str:
    cleaned = target_type.strip().lower()
    if cleaned not in VALID_TARGET_TYPES:
        allowed = ", ".join(sorted(VALID_TARGET_TYPES))
        raise DomainValidationError(f"invalid target_type: {target_type}. Allowed: {allowed}")
    return cleaned


def validate_moderation_action(action: str) -> str:
    cleaned = action.strip().lower()
    if cleaned not in VALID_MODERATION_ACTIONS:
        allowed = ", ".join(sorted(VALID_MODERATION_ACTIONS))
        raise DomainValidationError(f"invalid moderation action: {action}. Allowed: {allowed}")
    return cleaned


@dataclass(frozen=True)
class UserAdminSummary:
    user_id: int
    full_name: str
    email: str
    phone: str | None
    role: str
    status: str
    preferred_language: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_onboarded: bool = False
    onboarding: dict | None = None


@dataclass(frozen=True)
class SystemStats:
    total_users: int
    active_users: int
    total_sessions: int
    completed_sessions: int
    total_questions: int
    total_revenue: float


@dataclass(frozen=True)
class AuditLogEntry:
    audit_id: int
    user_id: int | None
    table_name: str
    record_id: int | None
    action: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime | None


@dataclass(frozen=True)
class ModerationItem:
    log_id: int
    admin_id: int
    target_type: str
    target_id: int | None
    action: str
    reason: str | None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_target_type(self.target_type)
        validate_moderation_action(self.action)


@dataclass(frozen=True)
class PaymentAdminItem:
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
