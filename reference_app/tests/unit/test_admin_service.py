from __future__ import annotations

import pytest

from app.application.admin.service import AdminService
from app.domain.admin import AuditLogEntry, SystemStats, UserAdminSummary
from app.domain.errors import DomainValidationError, NotFoundError


class FakeAdminRepo:
    def __init__(self) -> None:
        self.users: dict[int, UserAdminSummary] = {}
        self.audits: list[AuditLogEntry] = []
        self.next_audit_id = 1

    def list_users(self, session, *, search=None, role=None, status=None, limit=50, offset=0):
        items = list(self.users.values())
        if search:
            s = search.lower()
            items = [u for u in items if s in u.full_name.lower() or s in u.email.lower()]
        if role:
            items = [u for u in items if u.role == role]
        if status:
            items = [u for u in items if u.status == status]
        return items[offset:offset + limit]

    def count_users(self, session, *, search=None, role=None, status=None):
        return len(self.list_users(session, search=search, role=role, status=status, limit=1000, offset=0))

    def get_user_by_id(self, session, user_id: int):
        return self.users.get(user_id)

    def update_user_status(self, session, user_id: int, status: str):
        u = self.users[user_id]
        updated = UserAdminSummary(
            user_id=u.user_id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            role=u.role,
            status=status,
            preferred_language=u.preferred_language,
        )
        self.users[user_id] = updated
        return updated

    def update_user_role(self, session, user_id: int, role: str):
        u = self.users[user_id]
        updated = UserAdminSummary(
            user_id=u.user_id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            role=role,
            status=u.status,
            preferred_language=u.preferred_language,
        )
        self.users[user_id] = updated
        return updated

    def get_system_stats(self, session):
        return SystemStats(
            total_users=len(self.users),
            active_users=len([u for u in self.users.values() if u.status == "active"]),
            total_sessions=10,
            completed_sessions=8,
            total_questions=25,
            total_revenue=150.0,
        )

    def list_audit_logs(self, session, *, table_name=None, limit=50, offset=0):
        items = self.audits
        if table_name:
            items = [a for a in items if a.table_name == table_name]
        return items[offset:offset + limit]

    def count_audit_logs(self, session, *, table_name=None):
        return len(self.list_audit_logs(session, table_name=table_name, limit=1000, offset=0))

    def record_audit(self, session, *, user_id, table_name, record_id, action, old_value=None, new_value=None):
        entry = AuditLogEntry(
            audit_id=self.next_audit_id,
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            created_at=None,
        )
        self.audits.insert(0, entry)
        self.next_audit_id += 1


@pytest.fixture
def admin_env():
    repo = FakeAdminRepo()
    service = AdminService(repo=repo)
    user_id = 1
    repo.users[user_id] = UserAdminSummary(
        user_id=user_id,
        full_name="Alice Candidate",
        email="alice@example.com",
        phone=None,
        role="candidate",
        status="active",
        preferred_language="vi",
    )
    admin_id = 99
    return service, repo, user_id, admin_id


def test_list_users_and_search(admin_env):
    service, _, _, _ = admin_env
    items, total = service.get_users(None, search="alice")
    assert total == 1
    assert items[0].email == "alice@example.com"

    _, zero = service.get_users(None, search="bob")
    assert zero == 0


def test_update_user_status_with_audit(admin_env):
    service, repo, user_id, admin_id = admin_env
    updated = service.update_user_status(None, admin_id, user_id, "suspended")
    assert updated.status == "suspended"

    # Verify audit log was recorded
    assert len(repo.audits) == 1
    log = repo.audits[0]
    assert log.table_name == "users"
    assert log.record_id == user_id
    assert log.old_value == {"status": "active"}
    assert log.new_value == {"status": "suspended"}


def test_update_user_role(admin_env):
    service, repo, user_id, admin_id = admin_env
    updated = service.update_user_role(None, admin_id, user_id, "admin")
    assert updated.role == "admin"


def test_get_system_stats(admin_env):
    service, _, _, _ = admin_env
    stats = service.get_system_stats(None)
    assert stats.total_users == 1
    assert stats.total_sessions == 10
    assert stats.total_revenue == 150.0
