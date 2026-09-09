from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...application.auth.ports import StoredUser
from ...infrastructure.persistence.models.enums import Language, UserRole, UserStatus
from ...infrastructure.persistence.models.user import User


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _to_stored(row: User) -> StoredUser:
    return StoredUser(
        user_id=row.user_id,
        full_name=row.full_name,
        email=row.email,
        password_hash=row.password_hash,
        role=_enum_value(row.role),
        status=_enum_value(row.status),
    )


class SqlAlchemyUserRepository:
    def find_by_email(self, session: Any, email: str) -> StoredUser | None:
        row = session.execute(
            select(User).where(User.email == email),
        ).scalar_one_or_none()
        return _to_stored(row) if row is not None else None

    def find_by_id(self, session: Any, user_id: int) -> StoredUser | None:
        row = session.get(User, user_id)
        return _to_stored(row) if row is not None else None

    def add(
        self,
        session: Any,
        *,
        full_name: str,
        email: str,
        password_hash: str,
    ) -> StoredUser:
        row = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=UserRole.candidate,
            status=UserStatus.active,
            preferred_language=Language.vi,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_stored(row)
