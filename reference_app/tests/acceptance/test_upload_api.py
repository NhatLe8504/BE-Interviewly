from __future__ import annotations

import io
from unittest.mock import patch
import uuid

from app.application.storage.ports import UploadedFileResult


def unique_email(prefix: str = "uploader") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def get_authenticated_headers(client) -> dict[str, str]:
    email = unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Upload User", "email": email, "password": "password123"},
    )
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_endpoints_require_auth(client):
    res = client.post("/api/v1/upload")
    assert res.status_code == 401


def test_generic_upload_flow(client):
    headers = get_authenticated_headers(client)
    fake_result = UploadedFileResult(
        url="http://res.cloudinary.com/test/image/upload/sample.jpg",
        secure_url="https://res.cloudinary.com/test/image/upload/sample.jpg",
        public_id="interviewly/general/sample",
        format="jpg",
        resource_type="image",
        bytes=1024,
        status="success",
    )

    with patch.object(client.app.state.services.storage_service, "upload", return_value=fake_result):
        file_data = io.BytesIO(b"fake image bytes")
        response = client.post(
            "/api/v1/upload",
            files={"file": ("sample.jpg", file_data, "image/jpeg")},
            data={"folder": "interviewly/general", "resource_type": "image"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["secure_url"] == "https://res.cloudinary.com/test/image/upload/sample.jpg"
        assert body["public_id"] == "interviewly/general/sample"
        assert body["bytes"] == 1024


def test_upload_avatar_validation(client):
    headers = get_authenticated_headers(client)

    # Rejects disallowed extension
    file_bad = io.BytesIO(b"bad executable content")
    res_bad = client.post(
        "/api/v1/upload/avatar",
        files={"file": ("malware.exe", file_bad, "application/x-msdownload")},
        headers=headers,
    )
    assert res_bad.status_code == 400
    assert "Unsupported file extension" in res_bad.text

    # Accepts valid image extension
    fake_result = UploadedFileResult(
        url="http://res.cloudinary.com/test/avatar.png",
        secure_url="https://res.cloudinary.com/test/avatar.png",
        public_id="interviewly/avatars/user1_avatar",
        format="png",
        resource_type="image",
        bytes=2048,
        status="success",
    )
    with patch.object(client.app.state.services.storage_service, "upload", return_value=fake_result):
        file_ok = io.BytesIO(b"valid png content")
        res_ok = client.post(
            "/api/v1/upload/avatar",
            files={"file": ("avatar.png", file_ok, "image/png")},
            headers=headers,
        )
        assert res_ok.status_code == 200, res_ok.text
        assert res_ok.json()["secure_url"] == "https://res.cloudinary.com/test/avatar.png"


def test_upload_audio_validation(client):
    headers = get_authenticated_headers(client)

    fake_result = UploadedFileResult(
        url="http://res.cloudinary.com/test/answer.mp3",
        secure_url="https://res.cloudinary.com/test/answer.mp3",
        public_id="interviewly/audio/turn1_answer",
        format="mp3",
        resource_type="video",
        bytes=4096,
        status="success",
    )
    with patch.object(client.app.state.services.storage_service, "upload", return_value=fake_result):
        file_audio = io.BytesIO(b"valid mp3 audio content")
        res_audio = client.post(
            "/api/v1/upload/audio",
            files={"file": ("answer.mp3", file_audio, "audio/mpeg")},
            headers=headers,
        )
        assert res_audio.status_code == 200, res_audio.text
        assert res_audio.json()["secure_url"] == "https://res.cloudinary.com/test/answer.mp3"


def test_openapi_exposes_upload_paths(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/upload" in spec["paths"]
    assert "/api/v1/upload/avatar" in spec["paths"]
    assert "/api/v1/upload/audio" in spec["paths"]
    assert "/api/v1/upload/document" in spec["paths"]
