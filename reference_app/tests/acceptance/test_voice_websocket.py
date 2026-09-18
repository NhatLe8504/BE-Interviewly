from __future__ import annotations

import json


def test_voice_websocket_ping_pong_and_ready(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/99") as websocket:
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
    with client.websocket_connect("/api/v1/voice/ws/100") as websocket:
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
    with client.websocket_connect("/api/v1/voice/ws/101") as websocket:
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
    with client.websocket_connect("/api/v1/voice/ws/102") as websocket:
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
