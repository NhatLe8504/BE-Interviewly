from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base

if TYPE_CHECKING:
    from .session import InterviewSession
    from .catalog import QuestionBank


class InterviewSessionConfig(Base):
    __tablename__ = "interview_session_configs"
    __table_args__ = (
        Index("idx_session_config_session_stage", "session_id", "stage_key"),
    )

    config_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"), nullable=False,
    )
    stage_key: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="auto_random")
    min_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    selected_question_ids: Mapped[list[int] | None] = mapped_column(JSON)
    difficulty_filter: Mapped[int | None] = mapped_column(Integer)
    type_filter: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class SessionQuestionSelection(Base):
    __tablename__ = "session_question_selections"
    __table_args__ = (
        Index("idx_question_selection_session", "session_id", "stage_key"),
    )

    selection_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"), nullable=False,
    )
    stage_key: Mapped[str] = mapped_column(String(50), nullable=False)
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question_bank.question_id", ondelete="CASCADE"), nullable=False,
    )
    selection_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_at_turn: Mapped[int | None] = mapped_column(Integer)
    was_rerolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
