import os
import time
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from app.config import cleanup_stale_audio_files
from app.infrastructure.persistence.models.enums import SessionStatus
from app.infrastructure.persistence.models.session import InterviewSession
from app.infrastructure.persistence.models.jd_interview import JDGenerationJob


@pytest.fixture
def temp_audio_dir(tmp_path):
    audio_dir = tmp_path / "audio_storage"
    audio_dir.mkdir(parents=True, exist_ok=True)
    with patch("app.config.get_audio_storage_dir", return_value=audio_dir):
        yield audio_dir


def _set_folder_age(folder: Path, age_seconds: float):
    mtime = time.time() - age_seconds
    os.utime(folder, (mtime, mtime))


def test_cleanup_active_session_not_deleted(temp_audio_dir):
    session_dir = temp_audio_dir / "101"
    session_dir.mkdir()
    (session_dir / "turn_1.mp3").write_bytes(b"dummy")
    _set_folder_age(session_dir, 3600)  # 1 hour old

    mock_db = MagicMock()
    mock_session = MagicMock(spec=InterviewSession)
    mock_session.status = SessionStatus.in_progress
    mock_session.completed_at = None

    def get_mock(model, key):
        if model is InterviewSession and key == 101:
            return mock_session
        return None

    mock_db.get.side_effect = get_mock
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        max_age_seconds=86400,
        completed_ttl_seconds=1800,
        orphan_ttl_seconds=3600,
        session_factory=factory,
    )
    assert cleaned == 0
    assert session_dir.exists()


def test_cleanup_completed_session_deleted_after_ttl(temp_audio_dir):
    session_dir = temp_audio_dir / "102"
    session_dir.mkdir()
    (session_dir / "turn_1.mp3").write_bytes(b"dummy")
    _set_folder_age(session_dir, 2000)  # > 1800s TTL

    mock_db = MagicMock()
    mock_session = MagicMock(spec=InterviewSession)
    mock_session.status = SessionStatus.completed
    mock_session.completed_at = MagicMock()

    def get_mock(model, key):
        if model is InterviewSession and key == 102:
            return mock_session
        return None

    mock_db.get.side_effect = get_mock
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        max_age_seconds=86400,
        completed_ttl_seconds=1800,
        orphan_ttl_seconds=3600,
        session_factory=factory,
    )
    assert cleaned == 1
    assert not session_dir.exists()


def test_cleanup_completed_session_retained_before_ttl(temp_audio_dir):
    session_dir = temp_audio_dir / "103"
    session_dir.mkdir()
    (session_dir / "turn_1.mp3").write_bytes(b"dummy")
    _set_folder_age(session_dir, 300)  # 5 min < 1800s TTL

    mock_db = MagicMock()
    mock_session = MagicMock(spec=InterviewSession)
    mock_session.status = SessionStatus.completed
    mock_session.completed_at = MagicMock()

    def get_mock(model, key):
        if model is InterviewSession and key == 103:
            return mock_session
        return None

    mock_db.get.side_effect = get_mock
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        completed_ttl_seconds=1800,
        session_factory=factory,
    )
    assert cleaned == 0
    assert session_dir.exists()


def test_cleanup_orphan_folder_deleted_after_orphan_ttl(temp_audio_dir):
    orphan_dir = temp_audio_dir / "999"
    orphan_dir.mkdir()
    (orphan_dir / "turn_1.mp3").write_bytes(b"orphan")
    _set_folder_age(orphan_dir, 4000)  # > 3600s orphan TTL

    mock_db = MagicMock()
    mock_db.get.return_value = None
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        orphan_ttl_seconds=3600,
        session_factory=factory,
    )
    assert cleaned == 1
    assert not orphan_dir.exists()


def test_cleanup_orphan_folder_retained_before_orphan_ttl(temp_audio_dir):
    orphan_dir = temp_audio_dir / "998"
    orphan_dir.mkdir()
    (orphan_dir / "turn_1.mp3").write_bytes(b"orphan")
    _set_folder_age(orphan_dir, 500)  # < 3600s orphan TTL

    mock_db = MagicMock()
    mock_db.get.return_value = None
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        orphan_ttl_seconds=3600,
        session_factory=factory,
    )
    assert cleaned == 0
    assert orphan_dir.exists()


def test_cleanup_jd_job_completed_and_active(temp_audio_dir):
    # Completed JD job
    jd_completed = temp_audio_dir / "jd_job1"
    jd_completed.mkdir()
    (jd_completed / "audio.webm").write_bytes(b"data")
    _set_folder_age(jd_completed, 2000)  # > 1800s

    # Active JD job
    jd_active = temp_audio_dir / "jd_job2"
    jd_active.mkdir()
    (jd_active / "audio.webm").write_bytes(b"data")
    _set_folder_age(jd_active, 2000)

    job_completed = MagicMock(spec=JDGenerationJob)
    job_completed.status = "COMPLETED"

    job_active = MagicMock(spec=JDGenerationJob)
    job_active.status = "IN_PROGRESS"

    mock_db = MagicMock()

    def get_mock(model, key):
        if model is JDGenerationJob:
            if key in ("jd_job1", "job1"):
                return job_completed
            if key in ("jd_job2", "job2"):
                return job_active
        return None

    mock_db.get.side_effect = get_mock
    factory = MagicMock(return_value=mock_db)

    cleaned = cleanup_stale_audio_files(
        completed_ttl_seconds=1800,
        session_factory=factory,
    )
    assert cleaned == 1
    assert not jd_completed.exists()
    assert jd_active.exists()


def test_cleanup_repeated_runs_idempotent(temp_audio_dir):
    session_dir = temp_audio_dir / "104"
    session_dir.mkdir()
    (session_dir / "turn_1.mp3").write_bytes(b"dummy")
    _set_folder_age(session_dir, 2000)

    mock_db = MagicMock()
    mock_session = MagicMock(spec=InterviewSession)
    mock_session.status = SessionStatus.completed
    mock_session.completed_at = MagicMock()
    mock_db.get.return_value = mock_session
    factory = MagicMock(return_value=mock_db)

    # First run cleans
    cleaned1 = cleanup_stale_audio_files(completed_ttl_seconds=1800, session_factory=factory)
    assert cleaned1 == 1
    assert not session_dir.exists()

    # Second run does nothing and succeeds
    cleaned2 = cleanup_stale_audio_files(completed_ttl_seconds=1800, session_factory=factory)
    assert cleaned2 == 0


def test_cleanup_skips_symlinks(temp_audio_dir, tmp_path):
    outside_target = tmp_path / "outside_dir"
    outside_target.mkdir()
    (outside_target / "secret.txt").write_text("safe")

    symlink_dir = temp_audio_dir / "symlink_dir"
    try:
        symlink_dir.symlink_to(outside_target, target_is_directory=True)
    except OSError:
        # Windows non-admin or dev mode not enabled
        return

    _set_folder_age(symlink_dir, 5000)

    cleaned = cleanup_stale_audio_files(max_age_seconds=1000)
    assert outside_target.exists()
    assert (outside_target / "secret.txt").exists()
