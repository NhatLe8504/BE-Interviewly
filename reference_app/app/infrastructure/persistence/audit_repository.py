from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

from ...application.audit.ports import StoredAuditLog
from .models.enums import AuditAction
from .models.system import AuditLog as OrmAuditLog


def _to_stored_audit(row: OrmAuditLog) -> StoredAuditLog:
    action_str = row.action.value if hasattr(row.action, "value") else str(row.action)
    return StoredAuditLog(
        audit_id=row.audit_id,
        user_id=row.user_id,
        table_name=row.table_name,
        record_id=row.record_id,
        action=action_str,
        old_value=row.old_value,
        new_value=row.new_value,
        created_at=row.created_at,
    )


class SqlAlchemyAuditRepository:
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
        act = AuditAction(action) if action in AuditAction._value2member_map_ else AuditAction.insert
        row = OrmAuditLog(
            table_name=table_name,
            action=act,
            user_id=user_id,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_stored_audit(row)

    def list_logs(
        self,
        session: Any,
        *,
        user_id: int | None = None,
        table_name: str | None = None,
        limit: int = 50,
    ) -> list[StoredAuditLog]:
        stmt = select(OrmAuditLog)
        if user_id is not None:
            stmt = stmt.where(OrmAuditLog.user_id == user_id)
        if table_name is not None:
            stmt = stmt.where(OrmAuditLog.table_name == table_name)
        stmt = stmt.order_by(desc(OrmAuditLog.audit_id)).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_to_stored_audit(r) for r in rows]
