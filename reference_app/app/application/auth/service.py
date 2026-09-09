from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domain.errors import AuthError, ConflictError
from ...domain.identity import (
    normalize_email,
    validate_full_name,
    validate_password,
)
from .commands import LoginCommand, RegisterCommand
from .ports import (
    AuthUser,
    PasswordHasherPort,
    TokenIssuerPort,
    UserRepositoryPort,
    to_auth_user,
)


@dataclass
class AuthService:
    users: UserRepositoryPort
    hasher: PasswordHasherPort
    tokens: TokenIssuerPort

    def register(self, session: Any, command: RegisterCommand) -> AuthUser:
        full_name = validate_full_name(command.full_name)
        email = normalize_email(command.email)
        validate_password(command.password)
        if self.users.find_by_email(session, email) is not None:
            raise ConflictError("email already registered")
        stored = self.users.add(
            session,
            full_name=full_name,
            email=email,
            password_hash=self.hasher.hash(command.password),
        )
        return to_auth_user(stored)

    def login(self, session: Any, command: LoginCommand) -> tuple[str, AuthUser]:
        email = normalize_email(command.email)
        stored = self.users.find_by_email(session, email)
        if stored is None or not self.hasher.verify(command.password, stored.password_hash):
            raise AuthError("invalid email or password")
        return self.tokens.issue(stored.user_id), to_auth_user(stored)

    def get_user(self, session: Any, user_id: int) -> AuthUser:
        stored = self.users.find_by_id(session, user_id)
        if stored is None:
            raise AuthError("invalid token")
        return to_auth_user(stored)
