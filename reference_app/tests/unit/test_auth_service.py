from __future__ import annotations

import pytest

from app.application.auth.commands import LoginCommand, RegisterCommand
from app.application.auth.ports import StoredUser
from app.application.auth.service import AuthService
from app.domain.errors import AuthError, ConflictError, DomainValidationError


class FakeUsers:
    def __init__(self) -> None:
        self.rows: dict[str, StoredUser] = {}
        self.next_id = 1

    def find_by_email(self, session, email: str):
        return self.rows.get(email)

    def find_by_id(self, session, user_id: int):
        for row in self.rows.values():
            if row.user_id == user_id:
                return row
        return None

    def add(self, session, *, full_name: str, email: str, password_hash: str):
        row = StoredUser(
            user_id=self.next_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role="candidate",
            status="active",
        )
        self.next_id += 1
        self.rows[email] = row
        return row


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeTokens:
    def issue(self, user_id: int) -> str:
        return f"token-{user_id}"

    def parse(self, token: str) -> int:
        return int(token.rsplit("-", 1)[1])


def make_service() -> AuthService:
    return AuthService(users=FakeUsers(), hasher=FakeHasher(), tokens=FakeTokens())


def test_register_ok() -> None:
    service = make_service()
    user = service.register(
        None, RegisterCommand("Test User", "User@Example.com ", "password123"),
    )
    assert user.email == "user@example.com"
    assert user.role == "candidate"


def test_register_duplicate_email_conflicts() -> None:
    service = make_service()
    command = RegisterCommand("Test User", "dup@example.com", "password123")
    service.register(None, command)
    with pytest.raises(ConflictError):
        service.register(None, command)


def test_register_rejects_bad_input() -> None:
    service = make_service()
    with pytest.raises(DomainValidationError):
        service.register(None, RegisterCommand("Test", "not-an-email", "password123"))
    with pytest.raises(DomainValidationError):
        service.register(None, RegisterCommand("Test", "ok@example.com", "short"))


def test_login_ok_and_wrong_password() -> None:
    service = make_service()
    service.register(None, RegisterCommand("Test", "login@example.com", "password123"))
    token, user = service.login(
        None, LoginCommand("login@example.com", "password123"),
    )
    assert token == f"token-{user.user_id}"
    with pytest.raises(AuthError):
        service.login(None, LoginCommand("login@example.com", "wrong-pass"))
    with pytest.raises(AuthError):
        service.login(None, LoginCommand("missing@example.com", "password123"))
