"""HTTP round-trip thật giữa adapter và một server systemone cục bộ.

Chỉ server TypeSafe được thay bằng stub cục bộ (không có key thật để gọi
api.typesafe.ai); hình dạng request/response vẫn theo đúng OpenAPI.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.infrastructure.llm.jev_adapter import JevSystemOneAdapter


class _SystemOneHandler(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self):  # noqa: N802 - theo BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        _SystemOneHandler.received = {
            "payload": payload,
            "authorization": self.headers.get("Authorization"),
            "path": self.path,
        }
        answers = {
            "overall_match": {"type": "score", "score": 5.0, "confidence": 0.5, "legend": {}, "probabilities": {}},
            "verdict": {"type": "choice", "choice": "almost", "confidence": 0.6, "probabilities": {}},
        }
        for name in payload["questions"]:
            if name.startswith("skill__"):
                answers[name] = {"type": "score", "score": 3.0, "confidence": 0.6, "legend": {}, "probabilities": {}}
        body = json.dumps({
            "model": "jev-latest",
            "answers": answers,
            "usage": {"input_tokens": 100, "output_tokens": 10},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # giữ output test sạch
        pass


@pytest.fixture()
def systemone_server():
    server = HTTPServer(("127.0.0.1", 0), _SystemOneHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/systemone"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_adapter_http_round_trip(systemone_server):
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456", api_url=systemone_server)
    result = adapter.evaluate_readiness(
        job_title="Backend Engineer",
        job_seniority="middle",
        requirements=[
            {"skill_id": "python", "name": "Python", "importance": "must", "required_level": "middle"},
            {"skill_id": "sql", "name": "SQL", "importance": "must", "required_level": "middle"},
        ],
        candidate_skills={"python": {"level": "middle", "ability_score": 3.0, "confidence": 0.8}},
        cleaned_jd_text="JD ngắn.",
    )

    received = _SystemOneHandler.received
    assert received["path"] == "/v1/systemone"
    assert received["authorization"] == "Bearer test_real_key_123456"
    assert received["payload"]["model"] == "jev-latest"
    assert set(received["payload"]["questions"]) == {"overall_match", "verdict", "skill__python", "skill__sql"}

    assert result is not None
    # Thang điểm tổng 0..9 -> 5/9 = 56%.
    assert result.match_percent == 56
    assert result.verdict == "almost"
    assert result.skill_ratings["python"].status == "met"
