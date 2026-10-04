from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import enum
import hashlib
from typing import Any

from .errors import DomainValidationError


class JDSourceType(str, enum.Enum):
    file = "file"
    url = "url"
    text = "text"


class JDExtractionStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    partial = "partial"


class JDSeniorityLevel(str, enum.Enum):
    intern = "intern"
    fresher = "fresher"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    staff = "staff"
    principal = "principal"


class JDSectionType(str, enum.Enum):
    introduction = "introduction"
    behavioral = "behavioral"
    technical = "technical"
    scenario = "scenario"
    system_design = "system_design"
    role_specific = "role_specific"
    closing = "closing"


class JDJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    NORMALIZED = "NORMALIZED"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class JDErrorClassification(str, enum.Enum):
    non_retryable = "non_retryable"
    retryable_network = "retryable_network"
    schema_repairable = "schema_repairable"
    provider_error = "provider_error"
    business_error = "business_error"


VALID_SOURCE_TYPES = {s.value for s in JDSourceType}
VALID_SENIORITY_LEVELS = {s.value for s in JDSeniorityLevel}
VALID_JOB_STATUSES = {s.value for s in JDJobStatus}
VALID_SECTION_TYPES = {s.value for s in JDSectionType}


@dataclass(frozen=True)
class NormalizedJD:
    source_type: str
    raw_content: str
    cleaned_text: str
    checksum: str
    original_filename: str | None = None
    original_url: str | None = None
    language: str = "vi"
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source_type not in VALID_SOURCE_TYPES:
            raise DomainValidationError(f"Invalid source type: {self.source_type}")
        if not self.cleaned_text.strip():
            raise DomainValidationError("Cleaned JD text cannot be empty")
        if not self.checksum:
            raise DomainValidationError("Checksum cannot be empty")

    @classmethod
    def calculate_checksum(cls, text: str) -> str:
        normalized = " ".join(text.strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JobAnalysis:
    job_title: str
    seniority: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    domain_knowledge: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    technical_signals: list[str] = field(default_factory=list)
    behavioral_signals: list[str] = field(default_factory=list)
    confidence_score: float = 1.0
    company_name: str | None = None
    employment_type: str | None = None
    location: str | None = None

    def __post_init__(self) -> None:
        if not self.job_title.strip():
            raise DomainValidationError("Job title cannot be empty")
        if self.seniority not in VALID_SENIORITY_LEVELS:
            raise DomainValidationError(f"Invalid seniority level: {self.seniority}")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise DomainValidationError("Confidence score must be between 0.0 and 1.0")


@dataclass(frozen=True)
class BlueprintSection:
    section_type: str
    allocated_minutes: int
    target_competencies: list[str]
    question_count: int
    objective: str

    def __post_init__(self) -> None:
        if self.section_type not in VALID_SECTION_TYPES:
            raise DomainValidationError(f"Invalid section type: {self.section_type}")
        if self.allocated_minutes <= 0:
            raise DomainValidationError("Allocated minutes must be positive")
        if self.question_count <= 0:
            raise DomainValidationError("Question count must be positive")


@dataclass(frozen=True)
class InterviewBlueprint:
    target_role: str
    seniority: str
    total_duration_minutes: int
    target_difficulty: int
    objectives: list[str]
    competencies: list[str]
    sections: list[BlueprintSection]
    scoring_dimensions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.target_role.strip():
            raise DomainValidationError("Target role cannot be empty")
        if self.seniority not in VALID_SENIORITY_LEVELS:
            raise DomainValidationError(f"Invalid seniority level: {self.seniority}")
        if self.total_duration_minutes <= 0:
            raise DomainValidationError("Total duration must be positive")
        if not (1 <= self.target_difficulty <= 5):
            raise DomainValidationError("Target difficulty must be between 1 and 5")
        if not self.sections:
            raise DomainValidationError("Blueprint must have at least one section")


@dataclass(frozen=True)
class ScriptItem:
    order_index: int
    section_type: str
    competency_name: str
    question_text: str
    rationale: str
    difficulty: int
    expected_signals: list[str]
    red_flags: list[str]
    sample_good_answer: str | None = None
    follow_up_probes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.order_index < 1:
            raise DomainValidationError("Order index must be >= 1")
        if not self.question_text.strip():
            raise DomainValidationError("Question text cannot be blank")
        if not (1 <= self.difficulty <= 5):
            raise DomainValidationError("Difficulty must be between 1 and 5")


@dataclass(frozen=True)
class InterviewScript:
    script_id: str
    total_questions: int
    estimated_minutes: int
    items: list[ScriptItem]

    def __post_init__(self) -> None:
        if not self.script_id:
            raise DomainValidationError("Script ID cannot be empty")
        if self.total_questions < 0:
            raise DomainValidationError("Total questions cannot be negative")
        if len(self.items) != self.total_questions:
            raise DomainValidationError("Items count does not match total_questions")


@dataclass(frozen=True)
class JDGenerationJob:
    job_id: str
    user_id: int
    source_type: str
    checksum: str
    status: str = JDJobStatus.PENDING.value
    stage: str = "INITIALIZED"
    progress_pct: int = 0
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    session_id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.job_id:
            raise DomainValidationError("Job ID cannot be empty")
        if self.user_id <= 0:
            raise DomainValidationError("User ID must be positive")
        if self.status not in VALID_JOB_STATUSES:
            raise DomainValidationError(f"Invalid job status: {self.status}")
        if not (0 <= self.progress_pct <= 100):
            raise DomainValidationError("Progress percentage must be between 0 and 100")

    def update_stage(self, status: JDJobStatus, stage: str, progress_pct: int) -> JDGenerationJob:
        return JDGenerationJob(
            job_id=self.job_id,
            user_id=self.user_id,
            source_type=self.source_type,
            checksum=self.checksum,
            status=status.value,
            stage=stage,
            progress_pct=progress_pct,
            error_code=self.error_code,
            error_message=self.error_message,
            retry_count=self.retry_count,
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def mark_failed(self, error_code: str, error_message: str) -> JDGenerationJob:
        return JDGenerationJob(
            job_id=self.job_id,
            user_id=self.user_id,
            source_type=self.source_type,
            checksum=self.checksum,
            status=JDJobStatus.FAILED.value,
            stage="FAILED",
            progress_pct=self.progress_pct,
            error_code=error_code,
            error_message=error_message,
            retry_count=self.retry_count,
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def mark_completed(self, session_id: int | None = None) -> JDGenerationJob:
        return JDGenerationJob(
            job_id=self.job_id,
            user_id=self.user_id,
            source_type=self.source_type,
            checksum=self.checksum,
            status=JDJobStatus.COMPLETED.value,
            stage="COMPLETED",
            progress_pct=100,
            error_code=None,
            error_message=None,
            retry_count=self.retry_count,
            session_id=session_id or self.session_id,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
        )
