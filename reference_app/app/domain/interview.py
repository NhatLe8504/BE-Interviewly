from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import enum

from .errors import DomainValidationError


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class SessionMode(str, enum.Enum):
    text = "text"
    voice = "voice"


class ExperienceLevel(str, enum.Enum):
    intern = "intern"
    fresher = "fresher"
    junior = "junior"
    mid = "mid"
    senior = "senior"


class Language(str, enum.Enum):
    vi = "vi"
    en = "en"


class TurnSpeaker(str, enum.Enum):
    ai = "ai"
    candidate = "candidate"


VALID_STATUSES = {s.value for s in SessionStatus}
VALID_LEVELS = {l.value for l in ExperienceLevel}
VALID_LANGUAGES = {l.value for l in Language}
VALID_MODES = {m.value for m in SessionMode}


@dataclass(frozen=True)
class InterviewSession:
    session_id: int
    user_id: int
    domain_id: int | None = None
    role_id: int | None = None
    level: str = ExperienceLevel.fresher.value
    language: str = Language.vi.value
    mode: str = SessionMode.text.value
    barge_in_enabled: bool = False
    status: str = SessionStatus.in_progress.value
    total_score: Decimal | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise DomainValidationError("user_id must be positive")
        if self.level not in VALID_LEVELS:
            raise DomainValidationError(f"invalid level: {self.level}")
        if self.language not in VALID_LANGUAGES:
            raise DomainValidationError(f"invalid language: {self.language}")
        if self.mode not in VALID_MODES:
            raise DomainValidationError(f"invalid mode: {self.mode}")
        if not isinstance(self.barge_in_enabled, bool):
            raise DomainValidationError("barge_in_enabled must be a boolean")
        if self.status not in VALID_STATUSES:
            raise DomainValidationError(f"invalid status: {self.status}")
        if self.total_score is not None:
            if not (Decimal("0") <= self.total_score <= Decimal("100")):
                raise DomainValidationError("total_score must be between 0 and 100")
        if self.completed_at is not None and self.started_at is not None:
            if self.completed_at < self.started_at:
                raise DomainValidationError("completed_at cannot be earlier than started_at")

    @property
    def candidate_id(self) -> int:
        return self.user_id

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.in_progress.value

    def mark_completed(
        self, total_score: Decimal | None, completed_at: datetime,
    ) -> InterviewSession:
        if not self.is_active:
            raise DomainValidationError("only active sessions can be completed")
        return InterviewSession(
            session_id=self.session_id,
            user_id=self.user_id,
            domain_id=self.domain_id,
            role_id=self.role_id,
            level=self.level,
            language=self.language,
            mode=self.mode,
            barge_in_enabled=self.barge_in_enabled,
            status=SessionStatus.completed.value,
            total_score=total_score,
            started_at=self.started_at,
            completed_at=completed_at,
        )

    def mark_abandoned(self) -> InterviewSession:
        if not self.is_active:
            raise DomainValidationError("only active sessions can be abandoned")
        return InterviewSession(
            session_id=self.session_id,
            user_id=self.user_id,
            domain_id=self.domain_id,
            role_id=self.role_id,
            level=self.level,
            language=self.language,
            mode=self.mode,
            barge_in_enabled=self.barge_in_enabled,
            status=SessionStatus.abandoned.value,
            total_score=self.total_score,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


@dataclass(frozen=True)
class InterviewTurn:
    turn_id: int
    session_id: int
    turn_number: int
    question_text: str
    answer_text: str | None = None
    duration_seconds: float = 0.0
    audio_url: str | None = None
    speaker: str = TurnSpeaker.candidate.value

    def __post_init__(self) -> None:
        if self.session_id <= 0:
            raise DomainValidationError("session_id must be positive")
        if self.turn_number < 1:
            raise DomainValidationError("turn_number must be >= 1")
        if not self.question_text.strip():
            raise DomainValidationError("question_text must not be blank")
        if self.duration_seconds < 0.0:
            raise DomainValidationError("duration_seconds must be non-negative")

    def with_answer(
        self,
        answer_text: str,
        duration_seconds: float = 0.0,
        audio_url: str | None = None,
    ) -> InterviewTurn:
        cleaned_answer = answer_text.strip()
        if not cleaned_answer:
            raise DomainValidationError("answer_text must not be blank")
        return InterviewTurn(
            turn_id=self.turn_id,
            session_id=self.session_id,
            turn_number=self.turn_number,
            question_text=self.question_text,
            answer_text=cleaned_answer,
            duration_seconds=duration_seconds,
            audio_url=audio_url,
            speaker=self.speaker,
        )
