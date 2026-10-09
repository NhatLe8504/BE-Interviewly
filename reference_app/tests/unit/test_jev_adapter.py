"""Unit tests cho Jev System One adapter theo ĐÚNG giao thức OpenAPI thật.

Payload mẫu bám theo https://api.typesafe.ai/openapi.json:
request {model, state, questions} -> response {model, answers, usage}.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import urllib.error

from app.infrastructure.llm.jev_adapter import (
    JevSystemOneAdapter,
    MAX_JD_EXCERPT_CHARS,
    MAX_REQUIREMENTS_IN_STATE,
    MAX_SKILL_QUESTIONS,
)

REQUIREMENTS = [
    {"skill_id": "python", "name": "Python", "importance": "must", "required_level": "middle"},
    {"skill_id": "sql", "name": "SQL", "importance": "must", "required_level": "middle"},
    {"skill_id": "docker", "name": "Docker", "importance": "nice", "required_level": "junior"},
]
CANDIDATE_SKILLS = {
    "python": {"level": "senior", "ability_score": 4.1, "confidence": 0.9},
    "sql": {"level": "junior", "ability_score": 2.0, "confidence": 0.6},
}


def _fake_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps(body).encode("utf-8")
    response.__enter__.return_value = response
    return response


def _systemone_body(overall: float = 7.2, verdict: str = "almost", skills: dict | None = None) -> dict:
    answers: dict = {
        "overall_match": {
            "type": "score",
            "score": overall,
            "confidence": 0.8,
            "legend": {"0": "none", "10": "all met"},
            "probabilities": {"7": 0.8, "6": 0.2},
        },
        "verdict": {
            "type": "choice",
            "choice": verdict,
            "confidence": 0.7,
            "probabilities": {verdict: 0.7, "not_ready": 0.3},
        },
    }
    for skill_id, (score, confidence) in (skills or {}).items():
        answers[f"skill__{skill_id}"] = {
            "type": "score",
            "score": score,
            "confidence": confidence,
            "legend": {},
            "probabilities": {},
        }
    return {"model": "jev-latest", "answers": answers, "usage": {"input_tokens": 120, "output_tokens": 12}}


def test_jev_adapter_availability():
    assert not JevSystemOneAdapter(api_key="your_jev_api_key").is_available()
    assert not JevSystemOneAdapter(api_key="").is_available()
    assert not JevSystemOneAdapter(api_key="short").is_available()
    assert JevSystemOneAdapter(api_key="test_real_key_123456").is_available()


def test_jev_adapter_unavailable_returns_none_without_call():
    adapter = JevSystemOneAdapter(api_key="your_jev_api_key")
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is None
    mock_urlopen.assert_not_called()


def test_jev_payload_follows_systemone_protocol():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(_systemone_body())
        adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
            cleaned_jd_text="X" * 2000,
        )

    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://api.typesafe.ai/v1/systemone"
    assert request.get_header("Authorization") == "Bearer test_real_key_123456"
    payload = json.loads(request.data.decode("utf-8"))

    assert payload["model"] == "jev-latest"
    assert isinstance(payload["state"], dict)
    questions = payload["questions"]
    assert questions["overall_match"]["type"] == "score"
    # API thật giới hạn tối đa 10 mức điểm cho câu hỏi score.
    assert len(questions["overall_match"]["criteria"]) == 10
    assert questions["verdict"]["type"] == "choice"
    assert set(questions["verdict"]["criteria"]) == {"ready", "almost", "not_ready", "insufficient_data"}
    skill_questions = [name for name in questions if name.startswith("skill__")]
    assert set(skill_questions) == {"skill__python", "skill__sql", "skill__docker"}
    assert all(questions[name]["type"] == "score" for name in skill_questions)
    assert all(len(questions[name]["criteria"]) == 6 for name in skill_questions)

    state = payload["state"]
    assert state["job_title"] == "Backend Engineer"
    assert len(state["jd_excerpt"]) == MAX_JD_EXCERPT_CHARS
    assert state["verified_candidate_skills"]["python"]["level"] == "senior"
    python_req = next(item for item in state["requirements"] if item["skill_id"] == "python")
    assert python_req["importance"] == "must"
    assert python_req["required_level"] == "middle"
    assert python_req["candidate_verified_level"] == "senior"
    docker_req = next(item for item in state["requirements"] if item["skill_id"] == "docker")
    assert docker_req["candidate_verified_level"] == "none"


def test_jev_limits_skill_questions_and_state_size():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    many_requirements = [
        {"skill_id": f"skill{i}", "name": f"Skill {i}", "importance": "must", "required_level": "senior"}
        for i in range(20)
    ]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(_systemone_body())
        adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="senior",
            requirements=many_requirements,
            candidate_skills={},
        )
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    skill_questions = [name for name in payload["questions"] if name.startswith("skill__")]
    assert len(skill_questions) == MAX_SKILL_QUESTIONS
    assert len(payload["state"]["requirements"]) == MAX_REQUIREMENTS_IN_STATE


def test_jev_parses_score_and_choice_answers():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    body = _systemone_body(overall=7.2, verdict="almost", skills={"python": (4.2, 0.9), "sql": (1.6, 0.5), "docker": (0.2, 0.4)})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(body)
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )

    assert result is not None
    # Thang điểm tổng 0..9 -> 7.2/9 = 80%.
    assert result.match_percent == 80
    assert result.verdict == "almost"
    assert result.confidence == 0.8
    assert result.model == "jev-latest"
    assert result.skill_ratings["python"].status == "met"
    assert result.skill_ratings["sql"].status == "partial"
    assert result.skill_ratings["docker"].status == "unknown"
    # Dưới mức yêu cầu, xếp theo điểm tăng dần (docker thấp nhất).
    assert result.recommended_skills == ["docker", "sql"]
    assert "80%" in result.explanation
    assert "SQL" in result.explanation


def test_jev_invalid_verdict_is_derived_from_score():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    body = _systemone_body(overall=8.4, verdict="something_else")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(body)
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is not None
    assert result.verdict == "ready"
    assert result.match_percent == 93


def test_jev_missing_overall_answer_falls_back():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    body = _systemone_body()
    del body["answers"]["overall_match"]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(body)
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is None


def test_jev_malformed_body_falls_back():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response({"choices": [{"message": {"content": "legacy shape"}}]})
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is None


def test_jev_http_error_falls_back():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.typesafe.ai/v1/systemone",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is None


def test_jev_empty_requirements_skips_call():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=[],
            candidate_skills={},
        )
    assert result is None
    mock_urlopen.assert_not_called()


def test_jev_out_of_range_score_is_clamped():
    adapter = JevSystemOneAdapter(api_key="test_real_key_123456")
    body = _systemone_body(overall=42.0, verdict="ready")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response(body)
        result = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=REQUIREMENTS,
            candidate_skills=CANDIDATE_SKILLS,
        )
    assert result is not None
    assert result.match_percent == 100
