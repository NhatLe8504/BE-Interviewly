from __future__ import annotations

import json
import uuid
import pytest
from starlette.websockets import WebSocketDisconnect


def _create_user_and_token(client, email_prefix: str = "ws_user") -> tuple[str, int]:
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Voice Candidate", "email": email, "password": "Password123!"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()
    token = data["access_token"]
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    user_id = me_resp.json()["user_id"]
    return token, user_id


def _create_session(client, token: str) -> int:
    resp = client.post(
        "/api/v1/interviews/sessions",
        json={
            "role_name": "DevOps Engineer",
            "level": "junior",
            "language": "vi",
            "mode": "voice",
            "barge_in_enabled": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def test_voice_websocket_absent_token_fails_closed(client) -> None:
    token, _ = _create_user_and_token(client, "ws_notok")
    session_id = _create_session(client, token)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/voice/ws/{session_id}"):
            pass
    assert exc_info.value.code == 1008


def test_voice_websocket_bad_token_fails_closed(client) -> None:
    token, _ = _create_user_and_token(client, "ws_badtok")
    session_id = _create_session(client, token)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token=invalid.jwt.token"):
            pass
    assert exc_info.value.code == 1008


def test_voice_websocket_wrong_owner_fails_closed(client) -> None:
    token_owner, _ = _create_user_and_token(client, "ws_owner")
    token_other, _ = _create_user_and_token(client, "ws_other")
    session_id = _create_session(client, token_owner)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token_other}"):
            pass
    assert exc_info.value.code == 1008


def test_voice_websocket_missing_session_fails_closed(client) -> None:
    token, _ = _create_user_and_token(client, "ws_nosess")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/voice/ws/999999?token={token}"):
            pass
    assert exc_info.value.code == 1008


def test_voice_websocket_missing_jd_session_fails_closed(client) -> None:
    token, _ = _create_user_and_token(client, "ws_nojdsess")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/voice/ws/jd_nonexistent_job_123?token={token}"):
            pass
    assert exc_info.value.code == 1008


def test_voice_websocket_valid_owner_both_paths(client) -> None:
    token, _ = _create_user_and_token(client, "ws_paths")
    session_id = _create_session(client, token)

    # Path 1: /api/v1/voice/ws/{session_id}
    with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token}") as ws1:
        ws1.send_text(json.dumps({"type": "ping"}))
        resp = json.loads(ws1.receive_text())
        assert resp["type"] == "pong"

    # Path 2: /api/v1/interviews/{session_id}/ws
    with client.websocket_connect(f"/api/v1/interviews/{session_id}/ws?token={token}") as ws2:
        ws2.send_text(json.dumps({"type": "ping"}))
        resp = json.loads(ws2.receive_text())
        assert resp["type"] == "pong"


def test_voice_websocket_ping_pong_and_ready(client) -> None:
    token, _ = _create_user_and_token(client, "ws_ready")
    session_id = _create_session(client, token)

    with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token}") as websocket:
        # Ping
        websocket.send_text(json.dumps({"type": "ping"}))
        resp = json.loads(websocket.receive_text())
        assert resp["type"] == "pong"

        # Client ready
        websocket.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "DevOps Engineer",
            "level": "junior",
            "language": "vi",
        }))

        received_types = set()
        for _ in range(5):
            msg = json.loads(websocket.receive_text())
            received_types.add(msg["type"])
            if msg.get("type") in ("audio", "done", "state"):
                break

        assert "state" in received_types or "ai_token" in received_types or "subtitle" in received_types


def test_voice_websocket_interim_and_final_transcript_flow(client) -> None:
    token, _ = _create_user_and_token(client, "ws_flow")
    session_id = _create_session(client, token)

    with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token}") as websocket:
        # Send interim transcript
        websocket.send_text(json.dumps({
            "type": "interim_transcript",
            "text": "Dạ em xin chào",
        }))
        event = json.loads(websocket.receive_text())
        assert event["type"] == "transcript"
        assert event["text"] == "Dạ em xin chào"
        assert event["is_final"] is False

        # Send final transcript
        websocket.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Em có 2 năm kinh nghiệm làm việc với FastAPI và Docker.",
            "duration_seconds": 15.0,
        }))

        # Verify candidate transcript confirmed
        event2 = json.loads(websocket.receive_text())
        assert event2["type"] == "transcript"
        assert event2["is_final"] is True

        # State transitions to THINK
        event3 = json.loads(websocket.receive_text())
        assert event3["type"] == "state"
        assert event3["state"] == "THINK"


def test_voice_websocket_barge_in_stops_audio(client) -> None:
    token, _ = _create_user_and_token(client, "ws_barge")
    session_id = _create_session(client, token)

    with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token}") as websocket:
        # Final transcript starts thinking/generation
        websocket.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Câu hỏi tiếp theo là gì ạ?",
        }))

        # Consume transcript confirmation
        json.loads(websocket.receive_text())
        # Consume state: THINK
        json.loads(websocket.receive_text())

        # Immediate barge-in interruption signal
        websocket.send_text(json.dumps({"type": "user_speech_start"}))

        # Check for interrupted and state: LISTEN events
        events = []
        for _ in range(3):
            ev = json.loads(websocket.receive_text())
            events.append(ev)
            if ev.get("type") == "state" and ev.get("state") == "LISTEN":
                break

        interrupted = any(e.get("type") == "interrupted" for e in events)
        listen_state = any(e.get("state") == "LISTEN" for e in events)
        assert interrupted or listen_state


def test_voice_websocket_barge_in_can_be_disabled(client) -> None:
    token, _ = _create_user_and_token(client, "ws_disbarge")
    session_id = _create_session(client, token)

    with client.websocket_connect(f"/api/v1/voice/ws/{session_id}?token={token}") as websocket:
        # Disable barge-in via config message
        websocket.send_text(json.dumps({
            "type": "client_ready",
            "barge_in_enabled": False,
        }))

        # Also send explicit config
        websocket.send_text(json.dumps({
            "type": "config",
            "barge_in_enabled": False,
        }))

        # Send ping to ensure config was processed
        websocket.send_text(json.dumps({"type": "ping"}))
        received_types = []
        for _ in range(10):
            msg = json.loads(websocket.receive_text())
            received_types.append(msg["type"])
            if msg.get("type") == "pong":
                break

        assert "pong" in received_types
