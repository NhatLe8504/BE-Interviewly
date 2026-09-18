from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class VoiceClientReadyIn(BaseModel):
    type: Literal["client_ready"] = "client_ready"
    role_name: str | None = None
    level: str | None = None
    language: str | None = None
    voice: str | None = None
    barge_in_enabled: bool = True


class VoiceConfigIn(BaseModel):
    type: Literal["config", "set_barge_in"]
    barge_in_enabled: bool | None = None
    voice: str | None = None


class VoiceTranscriptIn(BaseModel):
    type: Literal["interim_transcript", "final_transcript"]
    text: str
    duration_seconds: float = 0.0


class VoiceStateOut(BaseModel):
    type: Literal["state"] = "state"
    state: str = Field(description="LISTEN, THINK, or SPEAK")
    turn_id: int
    generation_id: str = ""


class VoiceTranscriptOut(BaseModel):
    type: Literal["transcript"] = "transcript"
    role: str = "candidate"
    text: str
    is_final: bool = False
    turn_id: int


class VoiceAiTokenOut(BaseModel):
    type: Literal["ai_token"] = "ai_token"
    token: str
    turn_id: int
    generation_id: str


class VoiceSubtitleOut(BaseModel):
    type: Literal["subtitle"] = "subtitle"
    sentence: str
    sentence_index: int
    turn_id: int
    generation_id: str


class VoiceAudioChunkOut(BaseModel):
    type: Literal["audio"] = "audio"
    audio_data: str = Field(description="Base64 encoded MP3 audio chunk")
    mime_type: str = "audio/mpeg"
    sentence_index: int
    turn_id: int
    generation_id: str


class VoiceDoneOut(BaseModel):
    type: Literal["done"] = "done"
    turn_id: int
    generation_id: str
    full_text: str = ""
    is_completed: bool = False


class VoiceInterruptedOut(BaseModel):
    type: Literal["interrupted"] = "interrupted"
    generation_id: str
    turn_id: int
