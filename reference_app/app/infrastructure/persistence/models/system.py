from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base
from .enums import AuditAction

if TYPE_CHECKING:
    from .user import User


class ModerationLog(Base):
    __tablename__ = "moderation_logs"
    __table_args__ = (
        Index("idx_moderation_logs_target", "target_type", "target_id"),
    )

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    admin: Mapped["User"] = relationship(back_populates="moderation_actions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_logs_table_record", "table_name", "record_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"),
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"), nullable=False,
    )
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    user: Mapped["User | None"] = relationship(back_populates="audit_entries")
