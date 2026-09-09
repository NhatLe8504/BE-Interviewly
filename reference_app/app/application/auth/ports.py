from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredUser:
    user_id: int
    full_name: str
    email: str
    password_hash: str
    role: str
    status: str


@dataclass(frozen=True)
class AuthUser:
    user_id: int
    full_name: str
    email: str
    role: str
    status: str


def to_auth_user(stored: StoredUser) -> AuthUser:
    return AuthUser(
        user_id=stored.user_id,
        full_name=stored.full_name,
        email=stored.email,
        role=stored.role,
        status=stored.status,
    )


class UserRepositoryPort(Protocol):
    def find_by_email(self, session: Any, email: str) -> StoredUser | None:
        ...

    def find_by_id(self, session: Any, user_id: int) -> StoredUser | None:
        ...

    def add(
        self,
        session: Any,
        *,
        full_name: str,
        email: str,
        password_hash: str,
    ) -> StoredUser:
        ...


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str:
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        ...


class TokenIssuerPort(Protocol):
    def issue(self, user_id: int) -> str:
        ...

    def parse(self, token: str) -> int:
        ...
