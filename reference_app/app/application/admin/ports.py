from __future__ import annotations

from typing import Any, Protocol

from ...domain.admin import AuditLogEntry, SystemStats, UserAdminSummary


class AdminRepositoryPort(Protocol):
    def list_users(
        self,
        session: Any,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserAdminSummary]:
        ...

    def count_users(
        self,
        session: Any,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> int:
        ...

    def get_user_by_id(self, session: Any, user_id: int) -> UserAdminSummary | None:
        ...

    def update_user_status(self, session: Any, user_id: int, status: str) -> UserAdminSummary:
        ...

    def update_user_role(self, session: Any, user_id: int, role: str) -> UserAdminSummary:
        ...

    def get_system_stats(self, session: Any) -> SystemStats:
        ...

    def list_audit_logs(
        self,
        session: Any,
        *,
        table_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        ...

    def count_audit_logs(
        self,
        session: Any,
        *,
        table_name: str | None = None,
    ) -> int:
        ...

    def record_audit(
        self,
        session: Any,
        *,
        user_id: int | None,
        table_name: str,
        record_id: int | None,
        action: str,
        old_value: dict | None = None,
        new_value: dict | None = None,
    ) -> None:
        ...
