from __future__ import annotations

import logging

import base64
import json
from typing import Any
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from sqlalchemy.orm import Session
import re
from fastapi.security import HTTPAuthorizationCredentials
from ..dependencies import bearer_scheme, get_container, get_optional_user_id, get_session, require_admin
from ..schemas.voice import VoiceOptionsOut
from ....application.voice.voice_catalog import get_voice_catalog_options
from ....application.voice.entitlement import check_user_voice_entitlement

from ....application.container import ServiceContainer
from ....application.voice.orchestrator import VoiceInterviewOrchestrator
from ....infrastructure.llm.jev_turn_adapter import JevInterviewTurnJudge
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
    container: ServiceContainer = websocket.app.state.services

    # 1. Authenticate token before websocket.accept() (fail closed with 1008)
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token or not getattr(container, "auth_service", None):
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        authenticated_user_id = container.auth_service.tokens.parse(token)
    except Exception:
        # Do not log credential or token details
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    session_factory = getattr(container, "session_factory", None)
    if not session_factory:
        await websocket.close(code=1008, reason="Service unavailable")
        return

    # 2. Safely resolve session_id to integer (fail closed for missing/unresolvable IDs)
    session_id: int | None = None
    try:
        session_id = int(session_id_raw)
    except (ValueError, TypeError):
        if str(session_id_raw).startswith("jd_"):
            db_temp = session_factory()
            try:
                from ....infrastructure.persistence.models.jd_interview import JDGenerationJob
                job = db_temp.get(JDGenerationJob, str(session_id_raw))
                if job and job.session_id:
                    session_id = int(job.session_id)
            except Exception:
                pass
            finally:
                db_temp.close()

    if session_id is None:
        await websocket.close(code=1008, reason="Invalid session ID")
        return

    # 3. Verify session existence and owner authorization
    db_session = session_factory()
    session_obj = None
    role_name = "Software Engineer"
    level = "fresher"
    language = "vi"

    try:
        if container.interview_service:
            try:
                session_obj = container.interview_service.get_session(db_session, session_id)
            except Exception:
                session_obj = None

        if not session_obj:
            from ....infrastructure.persistence.models.session import InterviewSession as DbInterviewSession
            session_obj = db_session.get(DbInterviewSession, session_id)

        if not session_obj:
            await websocket.close(code=1008, reason="Session not found")
            return

        session_owner_id = getattr(session_obj, "user_id", None) or getattr(session_obj, "candidate_id", None)
        if session_owner_id != authenticated_user_id:
            await websocket.close(code=1008, reason="Forbidden")
            return

        if hasattr(session_obj, "level") and session_obj.level:
            level = session_obj.level.value if hasattr(session_obj.level, "value") else str(session_obj.level)
        elif hasattr(session_obj, "experience_level") and session_obj.experience_level:
            level = session_obj.experience_level.value if hasattr(session_obj.experience_level, "value") else str(session_obj.experience_level)

        if hasattr(session_obj, "language") and session_obj.language:
            language = session_obj.language.value if hasattr(session_obj.language, "value") else str(session_obj.language)

        role_id = getattr(session_obj, "role_id", None)
        if role_id:
            try:
                from ....infrastructure.persistence.models.catalog import JobRole
                role_rec = db_session.get(JobRole, role_id)
                if role_rec and role_rec.role_name:
                    role_name = role_rec.role_name
            except Exception:
                pass
    finally:
        db_session.close()

    # 4. Accept connection only after successful authentication and authorization
    await websocket.accept()
    connection = WebSocketVoiceConnection(websocket)

    # Use registered TTS & LLM voice stream adapters
    tts_adapter = getattr(container, "tts_adapter", None)
    llm_adapter = getattr(container, "llm_voice_adapter", None) or (
        container.interview_service.llm if container.interview_service else None
    )

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
        user_id=authenticated_user_id,
        turn_judge=JevInterviewTurnJudge(
            api_key=container.settings.jev_api_key,
            api_url=container.settings.jev_api_url,
            model=container.settings.jev_model,
        ),
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
                        role_name=role_name,
                        level=level,
                        language=language,
                        voice=data.get("voice"),
                        pitch=data.get("pitch", "+0Hz"),
                        barge_in_enabled=data.get("barge_in_enabled"),
                        selected_stages=data.get("selected_stages"),
                        questions_per_stage=data.get("questions_per_stage"),
                        persona_name=data.get("persona_name"),
                        company_name=data.get("company_name"),
                        mock_mode=data.get("mock_mode"),
                        response_mode=data.get("response_mode"),
                        total_duration_minutes=data.get("total_duration_minutes"),
                        browser_tts_fallback=bool(data.get("browser_tts_fallback")),
                        tts_fallback_lock=data.get("tts_fallback_lock"),
                    )

                elif msg_type in ("config", "set_barge_in"):
                    if data.get("response_mode") in ("voice", "text"):
                        orchestrator.response_mode = data["response_mode"]
                    if "browser_tts_fallback" in data:
                        orchestrator.set_browser_tts_preference(bool(data["browser_tts_fallback"]))
                    if "language" in data:
                        orchestrator.set_interview_language(data["language"])
                        await connection.send_event({
                            "type": "language_configured",
                            "language": orchestrator.language,
                        })
                    if "barge_in_enabled" in data:
                        orchestrator.set_barge_in_enabled(bool(data["barge_in_enabled"]))
                    if "voice" in data and data["voice"]:
                        orchestrator.set_voice(str(data["voice"]))
                        await connection.send_event({
                            "type": "voice_configured",
                            "voice": orchestrator.voice,
                        })
                    if "pitch" in data and data["pitch"] is not None:
                        orchestrator.set_pitch(data["pitch"])
                        await connection.send_event({
                            "type": "pitch_configured",
                            "pitch": orchestrator.pitch,
                        })
                    if "mock_mode" in data and data["mock_mode"]:
                        orchestrator.mock_mode = str(data["mock_mode"])

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
                        turn_id=data.get("turn_id"),
                    )

                elif msg_type == "playback_completed":
                    await orchestrator.handle_playback_completed(data.get("generation_id"))

                elif msg_type == "tts_fallback_consent" and isinstance(data.get("accepted"), bool):
                    await orchestrator.handle_tts_fallback_consent(
                        data.get("generation_id"), data["accepted"],
                    )

                elif msg_type == "stage_transition_confirm":
                    await orchestrator.handle_stage_transition_confirm(data.get("proposal_id"), data.get("stage_version"))

                elif msg_type == "stage_transition_defer":
                    await orchestrator.handle_stage_transition_defer(
                        data.get("continue_message"), data.get("proposal_id"), data.get("stage_version"),
                    )

                elif msg_type == "request_hint":
                    await orchestrator.handle_request_hint(data.get("question_id"))

                elif msg_type == "request_stage_transition":
                    await orchestrator.request_stage_transition()

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
        orchestrator.pause_flow()
        await orchestrator.cancel_current_generation()
        if orchestrator._judgment_task and not orchestrator._judgment_task.done():
            orchestrator._judgment_task.cancel()
        from ....domain.voice import VoiceSessionState
        if getattr(orchestrator, "state", None) == VoiceSessionState.COMPLETED:
            orchestrator._schedule_audio_cleanup(delay_seconds=60)


@router.websocket("/api/v1/voice/ws/{session_id}")
async def voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_voice_websocket_session(websocket, session_id)


@router.websocket("/api/v1/interviews/{session_id}/ws")
async def interview_voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_voice_websocket_session(websocket, session_id)


@router.get("/api/v1/admin/presence", tags=["admin"])
def get_presence_stats(admin_id: int = Depends(require_admin)):
    return {
        "online_count": presence_manager.get_online_count(),
        "online_user_ids": presence_manager.get_online_user_ids(),
    }


@router.websocket("/api/v1/ws/presence")
async def presence_websocket_endpoint(websocket: WebSocket):
    # Require admin authentication before accept
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    container: ServiceContainer = websocket.app.state.services
    if not token or not getattr(container, "auth_service", None):
        await websocket.close(code=1008, reason="Authentication token required")
        return

    try:
        user_id = container.auth_service.tokens.parse(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    session_factory = getattr(container, "session_factory", None)
    if not session_factory:
        await websocket.close(code=1008, reason="Service unavailable")
        return

    db_sess = session_factory()
    is_admin = False
    try:
        user = container.auth_service.get_user(db_sess, user_id)
        role_val = getattr(user.role, "value", str(user.role)) if getattr(user, "role", None) else ""
        if str(role_val).lower() == "admin":
            is_admin = True
    except Exception:
        pass
    finally:
        db_sess.close()

    if not is_admin:
        await websocket.close(code=1008, reason="Admin access required")
        return
    await websocket.accept()
    token = websocket.query_params.get("token")
    container: ServiceContainer = websocket.app.state.services

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
    container: ServiceContainer = Depends(get_container),
) -> VoiceOptionsOut:
    effective_user_id = user_id if user_id and user_id > 0 else None
    is_premium = check_user_voice_entitlement(session, effective_user_id) if effective_user_id else False
    api_key = getattr(container.settings, "elevenlabs_api_key", "")
    data = get_voice_catalog_options(
        is_premium, language=language, api_key=api_key,
        vieneu_available=bool(container.settings.vieneu_api_key),
    )
    return VoiceOptionsOut(**data)


@router.get("/api/v1/voice/preview")
async def preview_voice_sample(
    voice: str = "vi-VN-HoaiMyNeural",
    pitch: str = "+0Hz",
    text: str | None = None,
    user_id: int | None = Depends(get_optional_user_id),
    container: ServiceContainer = Depends(get_container),
):
    if voice.startswith("vieneu:"):
        if user_id is None:
            raise HTTPException(status_code=401, detail="Authentication required for VieNeu preview")
        if text:
            raise HTTPException(status_code=400, detail="Custom VieNeu preview text is not supported")
    sample_text = (text or "").strip()
    if not sample_text:
        if voice.startswith("en-"):
            sample_text = "Hello! I am your AI interviewer."
        elif voice.startswith("ja-"):
            sample_text = "こんにちは、AI面接官です。"
        elif voice.startswith("zh-"):
            sample_text = "你好！我是你的AI面试官。"
        elif voice.startswith("ko-"):
            sample_text = "안녕하세요! AI 면접관입니다."
        elif voice.startswith("fr-"):
            sample_text = "Bonjour ! Je suis votre recruteur IA."
        elif voice.startswith("de-"):
            sample_text = "Hallo! Ich bin dein KI-Interviewer."
        elif voice.startswith("es-"):
            sample_text = "¡Hola! Soy tu entrevistador de IA."
        else:
            sample_text = "Xin chào! Tôi là trợ lý phỏng vấn viên AI của bạn."

    tts = getattr(container, "tts_adapter", None)
    if not tts:
        raise HTTPException(status_code=500, detail="TTS service not configured")

    async def audio_generator():
        async for chunk in tts.synthesize_stream(sample_text, voice=voice, pitch=pitch):
            yield chunk

    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": "inline; filename=preview.mp3",
        },
    )


SAFE_AUDIO_FILENAME_REGEX = re.compile(r"^turn_\d+_(ai\.mp3|user\.(webm|wav|mp3|ogg|m4a|mp4))$")


@router.get("/api/v1/voice/audio/{session_id}/{filename}")
@router.head("/api/v1/voice/audio/{session_id}/{filename}")
async def get_turn_audio(
    session_id: str,
    filename: str,
    token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
):
    # 1. Filename format validation (fail closed against path traversal / arbitrary files)
    if not SAFE_AUDIO_FILENAME_REGEX.match(filename):
        raise HTTPException(status_code=400, detail="Invalid audio filename format")

    # 2. Session ID validation
    try:
        numeric_session_id = int(session_id)
        if numeric_session_id <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    # 3. Authenticate user from query param or Bearer header
    auth_token = token
    if not auth_token and credentials and credentials.credentials:
        auth_token = credentials.credentials

    if not auth_token or not getattr(container, "auth_service", None):
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        authenticated_user_id = container.auth_service.tokens.parse(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 4. Authorize session ownership
    from ....infrastructure.persistence.models.session import InterviewSession as DbInterviewSession
    session_rec = session.get(DbInterviewSession, numeric_session_id)
    if not session_rec:
        raise HTTPException(status_code=404, detail="Interview session not found")

    if session_rec.candidate_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 5. Path resolution beneath base_dir / session_id with traversal and symlink checks
    from ....config import get_audio_storage_dir
    base_dir = get_audio_storage_dir().resolve()
    session_dir = (base_dir / str(numeric_session_id)).resolve()
    if not session_dir.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid audio storage path")

    file_path = (session_dir / filename).resolve()
    if not file_path.is_relative_to(session_dir) or file_path.is_symlink():
        raise HTTPException(status_code=400, detail="Invalid audio file path")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".ogg"):
        media_type = "audio/ogg"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    elif filename.endswith(".m4a") or filename.endswith(".mp4"):
        media_type = "audio/mp4"
    else:
        media_type = "audio/webm"
    return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})


@router.post("/api/v1/interviews/sessions/{session_id}/turns/{turn_id}/user-audio")
async def upload_user_turn_audio(
    session_id: int,
    turn_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    container: ServiceContainer = Depends(get_container),
):
    # 1. Require authenticated user
    if not credentials or not credentials.credentials or not getattr(container, "auth_service", None):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        authenticated_user_id = container.auth_service.tokens.parse(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 2. Verify session ownership and active status
    from ....infrastructure.persistence.models.session import (
        InterviewSession as DbInterviewSession,
        InterviewTurn as OrmInterviewTurn,
    )
    from ....infrastructure.persistence.models.enums import SessionStatus

    session_rec = session.get(DbInterviewSession, session_id)
    if not session_rec:
        raise HTTPException(status_code=404, detail="Interview session not found")

    if session_rec.candidate_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if session_rec.status in (SessionStatus.completed, SessionStatus.abandoned) or str(session_rec.status).lower() in ("completed", "abandoned", "cancelled"):
        raise HTTPException(status_code=409, detail="Cannot upload audio to a completed or cancelled session")

    # 3. Verify turn ownership/existence before writing files
    turn_rec = (
        session.query(OrmInterviewTurn)
        .filter_by(session_id=session_id, turn_number=turn_id)
        .first()
    )
    if not turn_rec:
        raise HTTPException(status_code=404, detail="Interview turn not found")

    # 4. Validate audio file size and media type
    MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB limit
    content = await file.read(MAX_AUDIO_SIZE + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio file exceeds maximum size limit of 25MB")

    raw_content_type = (file.content_type or "").lower().strip()
    base_content_type = raw_content_type.split(";")[0].strip()
    allowed_types = {
        "audio/webm",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "video/webm",
        "video/mp4",
        "application/octet-stream",
    }
    if base_content_type and base_content_type not in allowed_types:
        raise HTTPException(status_code=415, detail=f"Unsupported audio media type: {file.content_type}")

    # 5. Restrict to server-issued filename & resolve beneath session directory
    ext = "webm"
    if base_content_type == "audio/ogg":
        ext = "ogg"
    elif base_content_type in ("audio/mpeg", "audio/mp3"):
        ext = "mp3"
    elif base_content_type in ("audio/wav", "audio/x-wav", "audio/wave"):
        ext = "wav"
    elif base_content_type in ("audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "video/mp4"):
        ext = "mp4"
    elif file.filename and "." in file.filename:
        file_ext = file.filename.rsplit(".", 1)[-1].lower()
        if file_ext in {"webm", "ogg", "wav", "mp3", "m4a", "mp4"}:
            ext = file_ext

    filename = f"turn_{turn_id}_user.{ext}"
    from ....config import get_audio_storage_dir
    base_dir = get_audio_storage_dir().resolve()
    session_dir = (base_dir / str(session_id)).resolve()
    if not session_dir.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid audio storage path")

    session_dir.mkdir(parents=True, exist_ok=True)
    file_path = (session_dir / filename).resolve()
    if not file_path.is_relative_to(session_dir) or file_path.is_symlink():
        raise HTTPException(status_code=400, detail="Invalid audio file path")

    file_path.write_bytes(content)
    audio_url = f"/api/v1/voice/audio/{session_id}/{filename}"

    turn_rec.user_audio_url = audio_url
    session.commit()

    return {"status": "ok", "audio_url": audio_url}
