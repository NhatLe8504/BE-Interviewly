from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import DomainValidationError

VALID_USER_STATUSES = frozenset({"active", "suspended", "deleted"})
VALID_USER_ROLES = frozenset({"candidate", "admin"})


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
