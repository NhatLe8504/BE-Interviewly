from __future__ import annotations

from unittest.mock import MagicMock, patch
from app.infrastructure.redis_client import check_redis, create_redis_client
from app.infrastructure.storage.cloudinary_storage import CloudinaryStorageService


def test_check_redis_with_none_returns_down():
    assert check_redis(None) == "down"


def test_check_redis_with_ping():
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    assert check_redis(mock_client) == "up"

    mock_client.ping.side_effect = Exception("Connection refused")
    assert check_redis(mock_client) == "down"


def test_cloudinary_storage_unconfigured():
    storage = CloudinaryStorageService()
    assert storage.configured is False
    res = storage.upload(b"dummy content", public_id="test_id")
    assert res.status == "not_configured"
    assert res.public_id == "test_id"


def test_cloudinary_storage_configured():
    with patch("cloudinary.config") as mock_cfg, patch("cloudinary.uploader.upload") as mock_upload:
        mock_upload.return_value = {"secure_url": "https://res.cloudinary.com/test.png"}
        storage = CloudinaryStorageService(
            cloud_name="test_cloud",
            api_key="12345",
            api_secret="secret",
        )
        assert storage.configured is True
        mock_cfg.assert_called_once()
        result = storage.upload(b"dummy content", folder="test_folder")
        assert result.secure_url == "https://res.cloudinary.com/test.png"
