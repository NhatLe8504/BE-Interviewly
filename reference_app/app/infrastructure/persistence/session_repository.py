from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ...application.interview.ports import InterviewSessionRepoPort, InterviewTurnRepoPort
from ...domain.interview import (
    ExperienceLevel,
    InterviewSession,
    InterviewTurn,
    Language,
    SessionMode,
    SessionStatus,
    TurnSpeaker,
)
from .models.session import (
    InterviewSession as DbSession,
    InterviewTurn as DbTurn,
)


def _to_domain_session(row: DbSession) -> InterviewSession:
    return InterviewSession(
        session_id=row.session_id,
        user_id=row.candidate_id,
        domain_id=row.domain_id,
        role_id=row.role_id,
        level=row.experience_level.value if row.experience_level else "fresher",
        language=row.language.value if row.language else "vi",
        mode=row.mode.value if row.mode else "text",
        status=row.status.value if row.status else "in_progress",
        total_score=row.total_score,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _to_domain_turn(row: DbTurn) -> InterviewTurn:
    return InterviewTurn(
        turn_id=row.turn_id,
        session_id=row.session_id,
        turn_number=row.turn_number,
        question_text=row.message_text or "",
        answer_text=row.transcribed_text,
        audio_url=row.audio_url,
        speaker=row.speaker.value if row.speaker else "candidate",
    )


class SqlAlchemySessionRepository(InterviewSessionRepoPort, InterviewTurnRepoPort):
    def create(self, session: Any, data: InterviewSession) -> InterviewSession:
        db_item = DbSession(
            candidate_id=data.user_id,
            domain_id=data.domain_id,
            role_id=data.role_id,
            experience_level=ExperienceLevel(data.level),
            language=Language(data.language),
            mode=SessionMode(data.mode),
            status=SessionStatus(data.status),
            total_score=data.total_score,
            started_at=data.started_at or datetime.now(timezone.utc),
        )
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
        return _to_domain_session(db_item)

    def find_by_id(self, session: Any, session_id: int) -> InterviewSession | None:
        row = session.get(DbSession, session_id)
        return _to_domain_session(row) if row is not None else None

    def update(self, session: Any, data: InterviewSession) -> InterviewSession:
        row = session.get(DbSession, data.session_id)
        if row is not None:
            row.status = SessionStatus(data.status)
            row.total_score = data.total_score
            row.completed_at = data.completed_at
            session.commit()
            session.refresh(row)
            return _to_domain_session(row)
        return data

    def list_by_user(self, session: Any, user_id: int) -> list[InterviewSession]:
        stmt = select(DbSession).where(DbSession.candidate_id == user_id).order_by(DbSession.started_at.desc())
        rows = session.scalars(stmt).all()
        return [_to_domain_session(r) for r in rows]

    def add_turn(self, session: Any, turn: InterviewTurn) -> InterviewTurn:
        speaker_val = TurnSpeaker(turn.speaker) if turn.speaker in TurnSpeaker._value2member_map_ else TurnSpeaker.candidate
        db_turn = DbTurn(
            session_id=turn.session_id,
            turn_number=turn.turn_number,
            speaker=speaker_val,
            message_text=turn.question_text,
            transcribed_text=turn.answer_text,
            audio_url=turn.audio_url,
        )
        session.add(db_turn)
        session.commit()
        session.refresh(db_turn)
        return _to_domain_turn(db_turn)

    def find_by_session_id(self, session: Any, session_id: int) -> list[InterviewTurn]:
        stmt = select(DbTurn).where(DbTurn.session_id == session_id).order_by(DbTurn.turn_number.asc())
        rows = session.scalars(stmt).all()
        return [_to_domain_turn(r) for r in rows]

    def find_turn(self, session: Any, session_id: int, turn_number: int) -> InterviewTurn | None:
        stmt = select(DbTurn).where(DbTurn.session_id == session_id, DbTurn.turn_number == turn_number)
        row = session.scalar(stmt)
        return _to_domain_turn(row) if row is not None else None

    def update_turn(self, session: Any, turn: InterviewTurn) -> InterviewTurn:
        stmt = select(DbTurn).where(DbTurn.session_id == turn.session_id, DbTurn.turn_number == turn.turn_number)
        row = session.scalar(stmt)
        if row is not None:
            row.transcribed_text = turn.answer_text
            row.audio_url = turn.audio_url
            session.commit()
            session.refresh(row)
            return _to_domain_turn(row)
        return turn
