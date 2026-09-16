from __future__ import annotations

from typing import Any

from ...domain.admin import (
    AuditLogEntry,
    SystemStats,
    UserAdminSummary,
    validate_user_role,
    validate_user_status,
)
from ...domain.errors import NotFoundError
from .ports import AdminRepositoryPort


class AdminService:
    def __init__(self, repo: AdminRepositoryPort) -> None:
        self.repo = repo

    def get_users(
        self,
        session: Any,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserAdminSummary], int]:
        if role is not None:
            validate_user_role(role)
        if status is not None:
            validate_user_status(status)

        items = self.repo.list_users(
            session, search=search, role=role, status=status, limit=limit, offset=offset,
        )
        total = self.repo.count_users(session, search=search, role=role, status=status)
        return items, total

    def update_user_status(
        self, session: Any, admin_id: int, user_id: int, status: str,
    ) -> UserAdminSummary:
        validate_user_status(status)
        existing = self.repo.get_user_by_id(session, user_id)
        if existing is None:
            raise NotFoundError(f"user {user_id} not found")

        updated = self.repo.update_user_status(session, user_id, status)
        self.repo.record_audit(
            session,
            user_id=admin_id,
            table_name="users",
            record_id=user_id,
            action="update",
            old_value={"status": existing.status},
            new_value={"status": status},
        )
        return updated

    def update_user_role(
        self, session: Any, admin_id: int, user_id: int, role: str,
    ) -> UserAdminSummary:
        validate_user_role(role)
        existing = self.repo.get_user_by_id(session, user_id)
        if existing is None:
            raise NotFoundError(f"user {user_id} not found")

        updated = self.repo.update_user_role(session, user_id, role)
        self.repo.record_audit(
            session,
            user_id=admin_id,
            table_name="users",
            record_id=user_id,
            action="update",
            old_value={"role": existing.role},
            new_value={"role": role},
        )
        return updated

    def get_system_stats(self, session: Any) -> SystemStats:
        return self.repo.get_system_stats(session)

    def get_audit_logs(
        self,
        session: Any,
        *,
        table_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]:
        items = self.repo.list_audit_logs(
            session, table_name=table_name, limit=limit, offset=offset,
        )
        total = self.repo.count_audit_logs(session, table_name=table_name)
        return items, total
