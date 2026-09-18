from __future__ import annotations

import json


def _drain_until(websocket, event_type, max_events=80):
    events = []
    for _ in range(max_events):
        try:
            msg = websocket.receive_text()
            ev = json.loads(msg)
            events.append(ev)
            if ev.get("type") == event_type:
                break
        except Exception:
            break
    return events


def _recv_n(websocket, n=10):
    events = []
    for _ in range(n):
        try:
            msg = websocket.receive_text()
            events.append(json.loads(msg))
        except Exception:
            break
    return events


def test_e2e_full_3_stage_interview(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/200") as ws:
        ws.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "Backend Engineer",
            "level": "senior",
            "language": "vi",
            "selected_stages": ["warmup", "technical", "closing"],
            "questions_per_stage": {"warmup": 1, "technical": 1, "closing": 1},
        }))

        # Drain all events until we see done (greeting flow)
        events = _drain_until(ws, "done")
        event_types = [e["type"] for e in events]

        # Must have stage_info
        assert "stage_info" in event_types, f"Missing stage_info. Got: {event_types}"
        si = next(e for e in events if e["type"] == "stage_info")
        assert si["current_stage"]["id"] == "warmup"
        assert si["current_stage"]["total"] == 3
        assert len(si["stages"]) == 3

        # Check state transitions
        states = [e["state"] for e in events if e["type"] == "state"]
        assert "THINK" in states

        # If done not in yet (async task), drain more
        if "done" not in event_types:
            more = _drain_until(ws, "done")
            events.extend(more)
            event_types = [e["type"] for e in events]

        assert "done" in event_types, f"Expected done. Got: {event_types}"

        # Answer warmup -> transition to technical
        ws.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Chao anh, em la Nguyen Van A, co 5 nam kinh nghiem Backend.",
            "duration_seconds": 12.0,
        }))
        events2 = _drain_until(ws, "done")
        event_types2 = [e["type"] for e in events2]
        assert "stage_change" in event_types2, f"Missing stage_change. Got: {event_types2}"
        sc = next(e for e in events2 if e["type"] == "stage_change")
        assert sc["stage_id"] == "technical"
        assert sc["stage_index"] == 2

        # Answer technical -> transition to closing
        ws.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Em da thiet ke kien truc microservices xu ly 10 trieu request moi ngay.",
            "duration_seconds": 15.0,
        }))
        events3 = _drain_until(ws, "done")
        assert "stage_change" in [e["type"] for e in events3]
        sc2 = next(e for e in events3 if e["type"] == "stage_change")
        assert sc2["stage_id"] == "closing"

        # Answer closing -> session completes
        ws.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Em mong muon muc luong khoang 30 trieu.",
            "duration_seconds": 10.0,
        }))
        # After final answer, session-finishing pipeline runs
        # It sends: transcript, state:THINK, stage events, ai_token*N, subtitle, audio*N, state:COMPLETED, done
        # The done event with is_completed=True should appear
        events4 = _drain_until(ws, "done", max_events=600)
        all_types = [e["type"] for e in events4]

        # Check for COMPLETED state as alternative signal
        completed = any(e.get("state") == "COMPLETED" for e in events4 if e["type"] == "state")
        done_events = [e for e in events4 if e["type"] == "done"]

        if done_events:
            assert done_events[-1]["is_completed"] is True
        else:
            # If done was not captured, at least COMPLETED state must be present
            assert completed, f"Expected done or COMPLETED. Types: {all_types}" 


def test_e2e_single_stage_technical_only(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/201") as ws:
        ws.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "Fullstack Developer",
            "level": "junior",
            "language": "en",
            "selected_stages": ["technical"],
            "questions_per_stage": {"technical": 1},
        }))
        events = _drain_until(ws, "done")
        si = next(e for e in events if e["type"] == "stage_info")
        assert si["current_stage"]["id"] == "technical"
        assert si["current_stage"]["total"] == 1
        assert si["current_stage"]["is_last"] is True

        ws.send_text(json.dumps({
            "type": "final_transcript",
            "text": "I designed a distributed event-driven system.",
            "duration_seconds": 10.0,
        }))
        events2 = _drain_until(ws, "done", max_events=300)
        all_types = [e["type"] for e in events2]
        done_events = [e for e in events2 if e["type"] == "done"]
        completed = any(e.get("state") == "COMPLETED" for e in events2 if e["type"] == "state")

        if done_events:
            assert done_events[-1]["is_completed"] is True
        else:
            assert completed, f"Expected done or COMPLETED. Types: {all_types}"
        # No stage_change because only 1 stage
        assert not any(e["type"] == "stage_change" for e in events2)


def test_e2e_two_stage_warmup_closing(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/202") as ws:
        ws.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "Product Manager",
            "level": "mid",
            "language": "vi",
            "selected_stages": ["warmup", "closing"],
            "questions_per_stage": {"warmup": 1, "closing": 1},
        }))
        events = _drain_until(ws, "done")
        si = next(e for e in events if e["type"] == "stage_info")
        assert si["current_stage"]["total"] == 2
        assert si["stages"][1]["id"] == "closing"

        ws.send_text(json.dumps({
            "type": "final_transcript",
            "text": "Chao anh, em rat vui.",
            "duration_seconds": 8.0,
        }))
        events2 = _drain_until(ws, "done")
        scs = [e for e in events2 if e["type"] == "stage_change"]
        assert len(scs) == 1
        assert scs[0]["stage_id"] == "closing"


def test_e2e_manual_next_stage(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/204") as ws:
        ws.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "Frontend Engineer",
            "level": "junior",
            "language": "vi",
            "selected_stages": ["warmup", "technical", "closing"],
        }))
        _drain_until(ws, "done")

        ws.send_text(json.dumps({"type": "next_stage"}))
        events = _drain_until(ws, "done")
        scs = [e for e in events if e["type"] == "stage_change"]
        assert len(scs) == 1
        assert scs[0]["stage_id"] == "technical"


def test_e2e_state_events_include_stage_data(client) -> None:
    with client.websocket_connect("/api/v1/voice/ws/205") as ws:
        ws.send_text(json.dumps({
            "type": "client_ready",
            "role_name": "ML Engineer",
            "level": "senior",
            "language": "vi",
            "selected_stages": ["warmup", "technical"],
        }))
        events = _drain_until(ws, "done")
        state_events = [e for e in events if e["type"] == "state"]
        assert len(state_events) >= 2
        for se in state_events:
            assert "current_stage" in se
            assert "stages" in se
            assert "turn_in_stage" in se
            assert "target_turns_in_stage" in se
