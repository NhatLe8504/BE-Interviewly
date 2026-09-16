from __future__ import annotations

import pytest

from app.domain.audit import AuditLog, ModerationLog
from app.domain.errors import DomainValidationError


def test_audit_log_valid():
    log = AuditLog(
        table_name="payment_transactions",
        action="insert",
        user_id=1,
        record_id=10,
        new_value={"status": "pending"},
    )
    assert log.table_name == "payment_transactions"
    assert log.action == "insert"
    assert log.user_id == 1
    assert log.new_value == {"status": "pending"}


def test_audit_log_invalid_action():
    with pytest.raises(DomainValidationError, match="invalid audit action"):
        AuditLog(table_name="users", action="drop")


def test_audit_log_blank_table():
    with pytest.raises(DomainValidationError, match="table_name must not be blank"):
        AuditLog(table_name="", action="insert")


def test_moderation_log_valid():
    mod = ModerationLog(
        admin_id=1,
        target_type="user",
        action="suspend",
        target_id=2,
        reason="violating terms",
    )
    assert mod.admin_id == 1
    assert mod.action == "suspend"


def test_moderation_log_invalid_admin():
    with pytest.raises(DomainValidationError, match="admin_id must be positive"):
        ModerationLog(admin_id=0, target_type="user", action="warn")
