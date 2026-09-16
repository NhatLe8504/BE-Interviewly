from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredAuditLog:
    audit_id: int
    user_id: int | None
    table_name: str
    record_id: int | None
    action: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime


class AuditLogRepoPort(Protocol):
    def log(
        self,
        session: Any,
        *,
        table_name: str,
        action: str,
        user_id: int | None = None,
        record_id: int | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> StoredAuditLog:
        ...

    def list_logs(
        self,
        session: Any,
        *,
        user_id: int | None = None,
        table_name: str | None = None,
        limit: int = 50,
    ) -> list[StoredAuditLog]:
        ...
