from unittest.mock import MagicMock, patch
import pytest

from app.infrastructure.llm.jev_adapter import JevSystemOneAdapter


def test_jev_adapter_availability():
    adapter_default = JevSystemOneAdapter(api_key="your_jev_api_key")
    assert not adapter_default.is_available()

    adapter_empty = JevSystemOneAdapter(api_key="")
    assert not adapter_empty.is_available()

    adapter_configured = JevSystemOneAdapter(api_key="test_real_key_123")
    assert adapter_configured.is_available()


def test_jev_adapter_fallback_on_unavailable():
    adapter = JevSystemOneAdapter(api_key="your_jev_api_key")
    result = adapter.evaluate_readiness(
        job_title="Backend Engineer",
        job_seniority="middle",
        requirements=[{"skill_id": "python", "importance": "must"}],
        candidate_skills={"python": {"level": "middle", "ability_score": 3.0, "confidence": 0.8}},
    )
    assert result is None


def test_jev_adapter_mock_response():
    adapter = JevSystemOneAdapter(api_key="valid_key")
    mock_resp_body = {
        "choices": [
            {
                "message": {
                    "content": "{\"match_percent\": 82, \"verdict\": \"almost_ready\", \"explanation\": \"Nền tảng tốt.\", \"recommended_skills\": [\"docker\"]}"
                }
            }
        ]
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = bytes(
            '{"choices":[{"message":{"content":"{\\"match_percent\\":82,\\"verdict\\":\\"almost_ready\\",\\"explanation\\":\\"Nền tảng tốt.\\",\\"recommended_skills\\":[\\"docker\\"]}"}}]}',
            "utf-8"
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = adapter.evaluate_readiness(
            job_title="Backend Engineer",
            job_seniority="middle",
            requirements=[],
            candidate_skills={},
        )
        assert res is not None
        assert res["match_percent"] == 82
        assert res["verdict"] == "almost_ready"
        assert res["recommended_skills"] == ["docker"]
