from __future__ import annotations

from dataclasses import dataclass, field
import enum

from .errors import DomainValidationError


class VoiceSessionState(str, enum.Enum):
    IDLE = "IDLE"
    LISTEN = "LISTEN"
    THINK = "THINK"
    SPEAK = "SPEAK"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class StageId(str, enum.Enum):
    WARMUP = "warmup"
    TECHNICAL = "technical"
    CLOSING = "closing"


@dataclass(frozen=True)
class InterviewStageDefinition:
    id: str
    name_vi: str
    name_en: str
    description_vi: str
    description_en: str
    subtopics_vi: list[str] = field(default_factory=list)
    subtopics_en: list[str] = field(default_factory=list)
    default_target_turns: int = 1


ALL_STAGE_DEFINITIONS: dict[str, InterviewStageDefinition] = {
    StageId.WARMUP.value: InterviewStageDefinition(
        id=StageId.WARMUP.value,
        name_vi="Khởi động & Chào hỏi",
        name_en="Warm-up & Greeting",
        description_vi="Chào hỏi, hỏi thăm bối cảnh & thời tiết, giới thiệu bản thân",
        description_en="Icebreaker, weather/context small talk, brief self-introduction",
        subtopics_vi=["Chào hỏi", "Trò chuyện ngắn (thời tiết / bối cảnh)", "Giới thiệu bản thân"],
        subtopics_en=["Greeting", "Small talk", "Self introduction"],
        default_target_turns=1,
    ),
    StageId.TECHNICAL.value: InterviewStageDefinition(
        id=StageId.TECHNICAL.value,
        name_vi="Phỏng vấn chuyên môn",
        name_en="Technical Interview",
        description_vi="Kinh nghiệm thực tế, câu hỏi kỹ thuật chuyên sâu & STAR",
        description_en="Hands-on experience, core technical challenges & follow-ups",
        subtopics_vi=["Kinh nghiệm thực tế", "Câu hỏi chuyên môn", "Câu hỏi tình huống & Follow-up"],
        subtopics_en=["Experience", "Technical questions", "Follow-up questions"],
        default_target_turns=2,
    ),
    StageId.CLOSING.value: InterviewStageDefinition(
        id=StageId.CLOSING.value,
        name_vi="Thỏa thuận & Chào kết",
        name_en="Closing & Negotiation",
        description_vi="Ứng viên đặt câu hỏi, nguyện vọng sự nghiệp & deal lương",
        description_en="Candidate Q&A, career expectation & salary negotiation",
        subtopics_vi=["Câu hỏi từ ứng viên", "Nguyện vọng sự nghiệp", "Trao đổi mức lương & chào kết"],
        subtopics_en=["Candidate questions", "Career expectation", "Salary / negotiation"],
        default_target_turns=1,
    ),
}


class VoiceEventType(str, enum.Enum):
    # Server -> Client
    STATE = "state"
    TRANSCRIPT = "transcript"
    AI_TOKEN = "ai_token"
    SUBTITLE = "subtitle"
    AUDIO = "audio"
    DONE = "done"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    PONG = "pong"
    STAGE_CHANGE = "stage_change"
    STAGE_INFO = "stage_info"
    QUESTION_CONTEXT = "question_context"
    QUESTION_REROLLED = "question_rerolled"

    # Client -> Server
    CLIENT_READY = "client_ready"
    USER_SPEECH_START = "user_speech_start"
    INTERIM_TRANSCRIPT = "interim_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    STOP_SESSION = "stop_session"
    PING = "ping"
    NEXT_STAGE = "next_stage"
    REROLL_QUESTION = "reroll_question"


VALID_STATES = {s.value for s in VoiceSessionState}


@dataclass(frozen=True)
class VoiceGenerationContext:
    session_id: int
    turn_id: int
    generation_id: str
    sentence_index: int = 0
    is_cancelled: bool = False

    def __post_init__(self) -> None:
        if self.session_id <= 0:
            raise DomainValidationError("session_id must be positive")
        if self.turn_id < 0:
            raise DomainValidationError("turn_id cannot be negative")
        if not self.generation_id.strip():
            raise DomainValidationError("generation_id must not be blank")

    def next_sentence(self) -> VoiceGenerationContext:
        return VoiceGenerationContext(
            session_id=self.session_id,
            turn_id=self.turn_id,
            generation_id=self.generation_id,
            sentence_index=self.sentence_index + 1,
            is_cancelled=self.is_cancelled,
        )

    def mark_cancelled(self) -> VoiceGenerationContext:
        return VoiceGenerationContext(
            session_id=self.session_id,
            turn_id=self.turn_id,
            generation_id=self.generation_id,
            sentence_index=self.sentence_index,
            is_cancelled=True,
        )


@dataclass(frozen=True)
class VoiceSentencePayload:
    sentence_index: int
    text: str
    generation_id: str
    turn_id: int
    is_last: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise DomainValidationError("sentence text must not be blank")
        if self.sentence_index < 0:
            raise DomainValidationError("sentence_index cannot be negative")
