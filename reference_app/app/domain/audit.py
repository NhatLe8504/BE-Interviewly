from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .errors import DomainValidationError

VALID_AUDIT_ACTIONS = {"insert", "update", "delete"}


@dataclass(frozen=True)
class AuditLog:
    table_name: str
    action: str
    user_id: int | None = None
    record_id: int | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    audit_id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.table_name or not self.table_name.strip():
            raise DomainValidationError("table_name must not be blank")
        if self.action not in VALID_AUDIT_ACTIONS:
            raise DomainValidationError(f"invalid audit action: {self.action}")
        if self.user_id is not None and self.user_id <= 0:
            raise DomainValidationError("user_id must be positive")


@dataclass(frozen=True)
class ModerationLog:
    admin_id: int
    target_type: str
    action: str
    target_id: int | None = None
    reason: str | None = None
    log_id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.admin_id <= 0:
            raise DomainValidationError("admin_id must be positive")
        if not self.target_type or not self.target_type.strip():
            raise DomainValidationError("target_type must not be blank")
        if not self.action or not self.action.strip():
            raise DomainValidationError("action must not be blank")
