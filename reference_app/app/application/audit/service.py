from __future__ import annotations

from typing import Any

from .ports import AuditLogRepoPort, StoredAuditLog


class AuditLogService:
    def __init__(self, audit_repo: AuditLogRepoPort) -> None:
        self.audit_repo = audit_repo

    def record(
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
        return self.audit_repo.log(
            session,
            table_name=table_name,
            action=action,
            user_id=user_id,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
        )

    def list_logs(
        self,
        session: Any,
        *,
        user_id: int | None = None,
        table_name: str | None = None,
        limit: int = 50,
    ) -> list[StoredAuditLog]:
        return self.audit_repo.list_logs(
            session, user_id=user_id, table_name=table_name, limit=limit,
        )
