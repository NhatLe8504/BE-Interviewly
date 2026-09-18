from __future__ import annotations

import base64
import json
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ....application.container import ServiceContainer
from ....application.voice.orchestrator import VoiceInterviewOrchestrator
from ....application.voice.ports import VoiceConnectionPort

router = APIRouter(tags=["voice"])


class WebSocketVoiceConnection(VoiceConnectionPort):
    """
    Adapter implementing VoiceConnectionPort over a FastAPI WebSocket.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._open = True

    def is_open(self) -> bool:
        return self._open

    async def send_event(self, event: dict[str, Any]) -> None:
        if not self._open:
            return
        try:
            payload = dict(event)
            if "audio_chunk" in payload and isinstance(payload["audio_chunk"], bytes):
                raw_bytes = payload.pop("audio_chunk")
                payload["audio_data"] = base64.b64encode(raw_bytes).decode("utf-8")
            await self.websocket.send_json(payload)
        except Exception:
            self._open = False


async def handle_voice_websocket_session(
    websocket: WebSocket,
    session_id: int,
) -> None:
    await websocket.accept()

    container: ServiceContainer = websocket.app.state.services
    connection = WebSocketVoiceConnection(websocket)

    # Optional auth token from query params: ?token=...
    token = websocket.query_params.get("token")
    user_id = 1
    if token and container.auth_service:
        try:
            user_id = container.auth_service.tokens.parse(token)
        except Exception:
            pass

    # Retrieve existing session details if available
    role_name = "Software Engineer"
    level = "fresher"
    language = "vi"

    session_factory = getattr(container, "session_factory", None)
    if container.interview_service and session_factory:
        db_session = session_factory()
        try:
            s = container.interview_service.get_session(db_session, session_id)
            if s:
                level = s.level
                language = s.language
        except Exception:
            pass
        finally:
            db_session.close()

    # Use registered TTS & LLM voice stream adapters
    tts_adapter = getattr(container, "tts_adapter", None)
    llm_adapter = getattr(container, "llm_voice_adapter", None) or container.interview_service.llm

    orchestrator = VoiceInterviewOrchestrator(
        session_id=session_id,
        connection=connection,
        tts=tts_adapter,
        llm=llm_adapter,
        role_name=role_name,
        level=level,
        language=language,
        voice="vi-VN-HoaiMyNeural" if language == "vi" else "en-US-JennyNeural",
        system_prompt=None,
        session_factory=session_factory,
    )

    try:
        while connection.is_open():
            message_raw = await websocket.receive_text()
            try:
                data = json.loads(message_raw)
            except Exception:
                await connection.send_event({
                    "type": "error",
                    "message": "Invalid JSON format",
                })
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await connection.send_event({"type": "pong"})

            elif msg_type == "client_ready":
                await orchestrator.handle_client_ready(
                    role_name=data.get("role_name"),
                    level=data.get("level"),
                    language=data.get("language"),
                    voice=data.get("voice"),
                    barge_in_enabled=data.get("barge_in_enabled"),
                    selected_stages=data.get("selected_stages"),
                    questions_per_stage=data.get("questions_per_stage"),
                )

            elif msg_type in ("config", "set_barge_in"):
                if "barge_in_enabled" in data:
                    orchestrator.set_barge_in_enabled(bool(data["barge_in_enabled"]))

            elif msg_type == "user_speech_start":
                await orchestrator.handle_user_speech_start()

            elif msg_type == "interim_transcript":
                await orchestrator.handle_interim_transcript(data.get("text", ""))

            elif msg_type == "final_transcript":
                await orchestrator.handle_final_transcript(
                    text=data.get("text", ""),
                    duration_seconds=float(data.get("duration_seconds", 0.0)),
                )

            elif msg_type == "next_stage":
                await orchestrator.handle_next_stage()

            elif msg_type == "reroll_question":
                await orchestrator.handle_reroll_question()

            elif msg_type == "stop_session":
                await orchestrator.handle_stop_session()
                break

    except WebSocketDisconnect:
        await orchestrator.cancel_current_generation()
    except Exception as exc:
        await connection.send_event({
            "type": "error",
            "message": str(exc),
        })
    finally:
        await orchestrator.cancel_current_generation()


@router.websocket("/api/v1/voice/ws/{session_id}")
async def voice_websocket_endpoint(websocket: WebSocket, session_id: int):
    await handle_voice_websocket_session(websocket, session_id)


@router.websocket("/api/v1/interviews/{session_id}/ws")
async def interview_voice_websocket_endpoint(websocket: WebSocket, session_id: int):
    await handle_voice_websocket_session(websocket, session_id)
