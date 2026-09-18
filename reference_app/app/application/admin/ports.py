from __future__ import annotations

from typing import Any, Protocol

from ...domain.admin import (
    AuditLogEntry,
    ModerationItem,
    SystemStats,
    UserAdminSummary,
)


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

    def list_moderation_logs(
        self,
        session: Any,
        *,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModerationItem]:
        ...

    def count_moderation_logs(
        self,
        session: Any,
        *,
        target_type: str | None = None,
    ) -> int:
        ...

    def add_moderation_log(
        self,
        session: Any,
        *,
        admin_id: int,
        target_type: str,
        action: str,
        target_id: int | None = None,
        reason: str | None = None,
    ) -> ModerationItem:
        ...


    def list_payments(
        self,
        session: Any,
        *,
        status: str | None = None,
        gateway: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaymentAdminItem]:
        ...

    def count_payments(
        self,
        session: Any,
        *,
        status: str | None = None,
        gateway: str | None = None,
    ) -> int:
        ...

    def get_payment_by_id(self, session: Any, transaction_id: int) -> PaymentAdminItem | None:
        ...
