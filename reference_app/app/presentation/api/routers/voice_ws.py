from __future__ import annotations

import logging

import base64
import json
from typing import Any
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session
from ..dependencies import get_container, get_optional_user_id, get_session
from ..schemas.voice import VoiceOptionsOut
from ....application.voice.voice_catalog import get_voice_catalog_options
from ....application.voice.entitlement import check_user_voice_entitlement

from ....application.container import ServiceContainer
from ....application.voice.orchestrator import VoiceInterviewOrchestrator
from ....application.voice.ports import VoiceConnectionPort

router = APIRouter(tags=["voice"])


class PresenceManager:
    def __init__(self) -> None:
        self.connected_users: dict[int, set[WebSocket]] = {}
        self.anonymous_sockets: set[WebSocket] = set()

    def connect(self, ws: WebSocket, user_id: int | None = None) -> None:
        if user_id:
            if user_id not in self.connected_users:
                self.connected_users[user_id] = set()
            self.connected_users[user_id].add(ws)
        else:
            self.anonymous_sockets.add(ws)

    def disconnect(self, ws: WebSocket, user_id: int | None = None) -> None:
        if user_id and user_id in self.connected_users:
            self.connected_users[user_id].discard(ws)
            if not self.connected_users[user_id]:
                del self.connected_users[user_id]
        self.anonymous_sockets.discard(ws)

    def get_online_count(self) -> int:
        count = len(self.connected_users) + len(self.anonymous_sockets)
        return max(1, count)

    def is_user_online(self, user_id: int) -> bool:
        return user_id in self.connected_users and len(self.connected_users[user_id]) > 0

    def get_online_user_ids(self) -> list[int]:
        return list(self.connected_users.keys())

    async def broadcast_state(self) -> None:
        msg = {
            "type": "presence_state",
            "online_count": self.get_online_count(),
            "online_user_ids": self.get_online_user_ids(),
        }
        all_sockets = [
            ws
            for sockets in self.connected_users.values()
            for ws in sockets
        ] + list(self.anonymous_sockets)

        for ws in all_sockets:
            try:
                await ws.send_json(msg)
            except Exception:
                pass


presence_manager = PresenceManager()



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
    session_id_raw: str | int,
) -> None:
    await websocket.accept()

    container: ServiceContainer = websocket.app.state.services
    session_factory = getattr(container, "session_factory", None)

    # Safely resolve session_id to integer
    session_id: int = 1
    try:
        session_id = int(session_id_raw)
    except (ValueError, TypeError):
        resolved = False
        if session_factory and str(session_id_raw).startswith("jd_"):
            db_temp = session_factory()
            try:
                from ....infrastructure.persistence.models.jd_interview import JDGenerationJob
                job = db_temp.get(JDGenerationJob, str(session_id_raw))
                if job and job.session_id:
                    session_id = int(job.session_id)
                    resolved = True
            except Exception:
                pass
            finally:
                db_temp.close()

        if not resolved:
            session_id = (abs(hash(str(session_id_raw))) % 1_000_000) + 1000

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
        evaluation_service=getattr(container, "evaluation_service", None),
        user_id=user_id,
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
            try:
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
                    if "language" in data:
                        orchestrator.set_interview_language(data["language"])
                        await connection.send_event({
                            "type": "language_configured",
                            "language": orchestrator.language,
                        })
                    if "barge_in_enabled" in data:
                        orchestrator.set_barge_in_enabled(bool(data["barge_in_enabled"]))
                    if "voice" in data and data["voice"]:
                        orchestrator.voice = str(data["voice"])
                        await connection.send_event({
                            "type": "voice_configured",
                            "voice": orchestrator.voice,
                        })

                elif msg_type == "abort":
                    await orchestrator.handle_user_speech_start(force=True)

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
            except Exception as handler_exc:
                logging.getLogger("VoiceWS").exception("Error handling websocket message %s: %s", msg_type, handler_exc)
                await connection.send_event({
                    "type": "error",
                    "message": f"Error handling {msg_type}: {handler_exc}",
                })

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
async def voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_voice_websocket_session(websocket, session_id)


@router.websocket("/api/v1/interviews/{session_id}/ws")
async def interview_voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_voice_websocket_session(websocket, session_id)


@router.get("/api/v1/admin/presence", tags=["admin"])
def get_presence_stats():
    return {
        "online_count": presence_manager.get_online_count(),
        "online_user_ids": presence_manager.get_online_user_ids(),
    }


@router.websocket("/api/v1/ws/presence")
async def presence_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    container: ServiceContainer = websocket.app.state.services
    user_id = None
    if token and container.auth_service:
        try:
            user_id = container.auth_service.tokens.parse(token)
        except Exception:
            pass

    presence_manager.connect(websocket, user_id)
    try:
        await websocket.send_json({
            "type": "presence_state",
            "online_count": presence_manager.get_online_count(),
            "online_user_ids": presence_manager.get_online_user_ids(),
        })
        await presence_manager.broadcast_state()

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        presence_manager.disconnect(websocket, user_id)
        await presence_manager.broadcast_state()



@router.get("/api/v1/voice/options", response_model=VoiceOptionsOut)
def get_voice_options(
    language: str | None = None,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
) -> VoiceOptionsOut:
    effective_user_id = user_id if user_id and user_id > 0 else None
    is_premium = check_user_voice_entitlement(session, effective_user_id) if effective_user_id else False
    data = get_voice_catalog_options(is_premium, language=language)
    return VoiceOptionsOut(**data)


@router.get("/api/v1/voice/audio/{session_id}/{filename}")
@router.head("/api/v1/voice/audio/{session_id}/{filename}")
async def get_turn_audio(session_id: str, filename: str):
    base_dir = Path("/srv/storage/audio")
    if not base_dir.exists():
        base_dir = Path(__file__).resolve().parents[4] / "storage" / "audio"
    file_path = base_dir / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/webm"
    return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})


@router.post("/api/v1/interviews/sessions/{session_id}/turns/{turn_id}/user-audio")
async def upload_user_turn_audio(
    session_id: int,
    turn_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user_id: int | None = Depends(get_optional_user_id),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    base_dir = Path("/srv/storage/audio")
    if not base_dir.exists():
        base_dir = Path(__file__).resolve().parents[4] / "storage" / "audio"
    session_dir = base_dir / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = f"turn_{turn_id}_user.webm"
    (session_dir / filename).write_bytes(content)
    audio_url = f"/api/v1/voice/audio/{session_id}/{filename}"

    from ....infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
    turn_rec = (
        session.query(OrmInterviewTurn)
        .filter_by(session_id=session_id, turn_number=turn_id)
        .first()
    )
    if turn_rec:
        turn_rec.user_audio_url = audio_url
        session.commit()

    return {"status": "ok", "audio_url": audio_url}
