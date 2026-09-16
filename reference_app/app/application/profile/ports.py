from __future__ import annotations

from typing import Any, Protocol

from ...domain.profile import UserProfile


class ProfileRepositoryPort(Protocol):
    def get_profile_by_user_id(self, session: Any, user_id: int) -> UserProfile | None:
        ...

    def update_profile(
        self,
        session: Any,
        user_id: int,
        *,
        full_name: str | None = None,
        phone: str | None = None,
        preferred_language: str | None = None,
        experience_level: str | None = None,
        target_domain_id: int | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> UserProfile:
        ...

    def get_password_hash(self, session: Any, user_id: int) -> str | None:
        ...

    def update_password(self, session: Any, user_id: int, new_password_hash: str) -> None:
        ...

    def domain_exists(self, session: Any, domain_id: int) -> bool:
        ...


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str:
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        ...
