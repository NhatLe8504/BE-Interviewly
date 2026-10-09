from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import DomainValidationError

ALLOWED_SOURCE_TYPES = {"interview_session", "practice_history", "jd_interview", "assessment"}
ALLOWED_INPUT_MODES = {"voice", "text", "quiz"}
ALLOWED_SKILL_LEVELS = {"none", "beginner", "intermediate", "advanced", "expert"}
ALLOWED_SENIORITY_LEVELS = {"none", "fresher", "junior", "middle", "senior", "lead"}


@dataclass(frozen=True)
class SkillEvidenceEvent:
    user_id: int
    skill_id: str
    source_type: str
    source_id: str
    score: float
    question_difficulty: int = 2
    grader_confidence: float = 0.85
    evidence_quote: str | None = None
    input_mode: str = "text"
    rubric_scores: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise DomainValidationError("user_id must be a positive integer")
        if not self.skill_id or not self.skill_id.strip():
            raise DomainValidationError("skill_id cannot be empty")
        if self.source_type not in ALLOWED_SOURCE_TYPES:
            raise DomainValidationError(f"source_type must be one of {ALLOWED_SOURCE_TYPES}")
        if not (0.0 <= self.score <= 1.0):
            raise DomainValidationError("score must be between 0.0 and 1.0")
        if not (1 <= self.question_difficulty <= 5):
            raise DomainValidationError("question_difficulty must be between 1 and 5")
        if not (0.0 <= self.grader_confidence <= 1.0):
            raise DomainValidationError("grader_confidence must be between 0.0 and 1.0")
        if self.input_mode not in ALLOWED_INPUT_MODES:
            raise DomainValidationError(f"input_mode must be one of {ALLOWED_INPUT_MODES}")


@dataclass(frozen=True)
class SkillEstimate:
    skill_id: str
    ability_score: float
    level: str
    confidence: float
    evidence_count: int
    max_difficulty_passed: int = 0
    last_evidence_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.level not in ALLOWED_SKILL_LEVELS:
            raise DomainValidationError(f"level must be one of {ALLOWED_SKILL_LEVELS}")
        if not (0.0 <= self.confidence <= 1.0):
            raise DomainValidationError("confidence must be between 0.0 and 1.0")
        if self.evidence_count < 0:
            raise DomainValidationError("evidence_count cannot be negative")


@dataclass(frozen=True)
class CareerProfile:
    user_id: int
    primary_role_track: str | None
    secondary_role_track: str | None
    role_confidence: float
    overall_level: str
    top_skills: list[dict[str, Any]] = field(default_factory=list)
    weak_skills: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise DomainValidationError("user_id must be a positive integer")
        if self.overall_level not in ALLOWED_SENIORITY_LEVELS:
            raise DomainValidationError(f"overall_level must be one of {ALLOWED_SENIORITY_LEVELS}")
        if not (0.0 <= self.role_confidence <= 1.0):
            raise DomainValidationError("role_confidence must be between 0.0 and 1.0")
