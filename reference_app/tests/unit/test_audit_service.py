from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pytest

from app.application.audit.ports import StoredAuditLog
from app.application.audit.service import AuditLogService


class FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list[StoredAuditLog] = []
        self._counter = 1

    def log(self, session: Any, **kwargs):
        log_id = self._counter
        self._counter += 1
        entry = StoredAuditLog(
            audit_id=log_id,
            user_id=kwargs.get("user_id"),
            table_name=kwargs["table_name"],
            record_id=kwargs.get("record_id"),
            action=kwargs["action"],
            old_value=kwargs.get("old_value"),
            new_value=kwargs.get("new_value"),
            created_at=datetime.now(timezone.utc),
        )
        self.entries.append(entry)
        return entry

    def list_logs(self, session: Any, **kwargs):
        res = list(self.entries)
        if kwargs.get("user_id") is not None:
            res = [r for r in res if r.user_id == kwargs["user_id"]]
        if kwargs.get("table_name") is not None:
            res = [r for r in res if r.table_name == kwargs["table_name"]]
        return res[: kwargs.get("limit", 50)]


def test_audit_service_record_and_list():
    repo = FakeAuditRepo()
    svc = AuditLogService(audit_repo=repo)

    entry = svc.record(
        None,
        table_name="payment_transactions",
        action="insert",
        user_id=5,
        record_id=101,
        new_value={"amount": "99000"},
    )
    assert entry.audit_id == 1
    assert entry.action == "insert"
    assert entry.user_id == 5

    logs = svc.list_logs(None, user_id=5)
    assert len(logs) == 1
    assert logs[0].table_name == "payment_transactions"
