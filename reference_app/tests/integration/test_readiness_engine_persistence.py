"""Readiness cache phải lưu và trả lại đúng nhãn engine (jev | heuristic)."""
from __future__ import annotations

import random

import pytest
from sqlalchemy import delete, select

from app.application.skills.service import UserSkillService
from app.config import Settings
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.orm import Base, create_session_factory
from app.infrastructure.persistence.models.job_aggregator import JobPostingRecord
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_skills import JobReadinessRecord


@pytest.fixture(scope="module")
def pg_session_factory():
    settings = Settings.from_env()
    try:
        engine = create_engine_from_url(settings.database_url)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
        pytest.skip(f"PostgreSQL không khả dụng cho integration test: {exc}")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class _DisabledJev:
    def is_available(self) -> bool:
        return False

    def evaluate_readiness(self, **kwargs):
        raise AssertionError("Jev không được gọi khi chưa cấu hình")


def test_readiness_engine_label_round_trips(pg_session_factory):
    lookup = pg_session_factory()
    try:
        job = None
        for candidate in lookup.scalars(select(JobPostingRecord).limit(200)).all():
            if candidate.skills_required:
                job = candidate
                break
        if job is None:
            pytest.skip("Không có job nào có skills_required để kiểm thử")
        job_id = job.job_id
    finally:
        lookup.close()

    user_id = random.randint(8_000_000_000, 8_999_999_999)
    setup = pg_session_factory()
    try:
        setup.add(User(
            user_id=user_id,
            full_name="Readiness Engine Test",
            email=f"readiness-engine-{user_id}@example.com",
            password_hash="not-used",
        ))
        setup.commit()
    finally:
        setup.close()

    try:
        session = pg_session_factory()
        try:
            svc = UserSkillService(session=session, jev_adapter=_DisabledJev())
            assessment = svc.evaluate_job_readiness(user_id=user_id, job_id=job_id, force_refresh=True)
        finally:
            session.close()
        assert assessment.analysis_engine == "heuristic"

        verify = pg_session_factory()
        try:
            record = verify.scalars(
                select(JobReadinessRecord).where(
                    JobReadinessRecord.user_id == user_id,
                    JobReadinessRecord.job_id == job_id,
                )
            ).first()
            assert record is not None, "readiness phải được lưu sau khi tính"
            assert record.analysis_engine == "heuristic"
            # Giả lập kết quả do Jev tạo để kiểm tra cột + nhánh cache.
            record.analysis_engine = "jev"
            verify.commit()
        finally:
            verify.close()

        session = pg_session_factory()
        try:
            svc = UserSkillService(session=session, jev_adapter=_DisabledJev())
            cached = svc.evaluate_job_readiness(user_id=user_id, job_id=job_id)
        finally:
            session.close()
        assert cached.analysis_engine == "jev"
    finally:
        cleanup = pg_session_factory()
        try:
            cleanup.execute(delete(User).where(User.user_id == user_id))
            cleanup.commit()
        finally:
            cleanup.close()
