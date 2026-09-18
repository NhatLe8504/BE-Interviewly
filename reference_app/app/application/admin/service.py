from __future__ import annotations

from typing import Any

from ...domain.admin import (
    AuditLogEntry,
    ModerationItem,
    SystemStats,
    UserAdminSummary,
    validate_moderation_action,
    validate_target_type,
    validate_user_role,
    validate_user_status,
)
from ...domain.errors import NotFoundError
from .commands import CreateModerationCommand
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

    def create_user(
        self,
        session: Any,
        admin_id: int,
        data: Any,
        hasher: Any,
    ) -> UserAdminSummary:
        validate_user_role(data.role)
        validate_user_status(data.status)
        password_hash = hasher.hash(data.password)
        created = self.repo.create_user(
            session,
            full_name=data.full_name,
            email=data.email,
            password_hash=password_hash,
            phone=data.phone,
            role=data.role,
            status=data.status,
            preferred_language=getattr(data, "preferred_language", "vi") or "vi",
        )
        self.repo.record_audit(
            session,
            user_id=admin_id,
            table_name="users",
            record_id=created.user_id,
            action="insert",
            old_value=None,
            new_value={"full_name": created.full_name, "email": created.email, "role": created.role, "status": created.status},
        )
        return created

    def get_user(self, session: Any, user_id: int) -> UserAdminSummary:
        user = self.repo.get_user_by_id(session, user_id)
        if user is None:
            raise NotFoundError(f"user {user_id} not found")
        return user

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

    def get_moderation_logs(
        self,
        session: Any,
        *,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ModerationItem], int]:
        if target_type is not None:
            validate_target_type(target_type)
        items = self.repo.list_moderation_logs(
            session, target_type=target_type, limit=limit, offset=offset,
        )
        total = self.repo.count_moderation_logs(session, target_type=target_type)
        return items, total

    def create_moderation_action(
        self,
        session: Any,
        admin_id: int,
        cmd: CreateModerationCommand,
    ) -> ModerationItem:
        validate_target_type(cmd.target_type)
        validate_moderation_action(cmd.action)
        return self.repo.add_moderation_log(
            session,
            admin_id=admin_id,
            target_type=cmd.target_type,
            action=cmd.action,
            target_id=cmd.target_id,
            reason=cmd.reason,
        )


    def get_payments(
        self,
        session: Any,
        *,
        status: str | None = None,
        gateway: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PaymentAdminItem], int]:
        items = self.repo.list_payments(session, status=status, gateway=gateway, limit=limit, offset=offset)
        total = self.repo.count_payments(session, status=status, gateway=gateway)
        return items, total

    def get_payment(self, session: Any, transaction_id: int) -> PaymentAdminItem:
        txn = self.repo.get_payment_by_id(session, transaction_id)
        if txn is None:
            raise NotFoundError(f"payment transaction {transaction_id} not found")
        return txn
