from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.application.cv.service import CvService
from app.domain.errors import ForbiddenError, NotFoundError
from app.infrastructure.orm import Base
from app.infrastructure.persistence.models.cv import CvDocumentRecord, CvGenerationJob
from app.infrastructure.persistence.models.user import User


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, CvDocumentRecord.__table__, CvGenerationJob.__table__])
    with Session(engine) as session:
        yield session


def test_delete_cv_success(db_session: Session):
    service = CvService(llm=None, clock=MagicMock())

    # Create user and CV
    user = User(user_id=1, email="test@example.com", full_name="Tester", password_hash="pw", role="candidate")
    cv = CvDocumentRecord(id=10, user_id=1, title="Test CV", template_id="minimalist_ats", color_theme="slate")
    db_session.add_all([user, cv])
    db_session.commit()

    # Create linked generation job
    job = CvGenerationJob(
        job_id="job-1",
        user_id=1,
        cv_id=10,
        job_title="Dev",
        jd_snapshot="Test JD",
        status="COMPLETED",
    )
    db_session.add(job)
    db_session.commit()

    # Delete CV
    service.delete_cv(db_session, user_id=1, cv_id=10)

    # Verify CV is deleted
    assert db_session.get(CvDocumentRecord, 10) is None
    # Verify job is unlinked
    db_session.refresh(job)
    assert job.cv_id is None


def test_delete_cv_idempotent_when_not_found(db_session: Session):
    service = CvService(llm=None, clock=MagicMock())
    # Should not raise exception if CV does not exist
    service.delete_cv(db_session, user_id=1, cv_id=999)


def test_delete_cv_forbidden_for_other_user(db_session: Session):
    service = CvService(llm=None, clock=MagicMock())
    user = User(user_id=1, email="u1@example.com", full_name="User 1", password_hash="pw", role="candidate")
    other = User(user_id=2, email="u2@example.com", full_name="User 2", password_hash="pw", role="candidate")
    cv = CvDocumentRecord(id=20, user_id=1, title="User 1 CV", template_id="minimalist_ats", color_theme="slate")
    db_session.add_all([user, other, cv])
    db_session.commit()

    with pytest.raises(ForbiddenError):
        service.delete_cv(db_session, user_id=2, cv_id=20)


def test_delete_cv_allowed_for_admin(db_session: Session):
    service = CvService(llm=None, clock=MagicMock())
    user = User(user_id=1, email="u1@example.com", full_name="User 1", password_hash="pw", role="candidate")
    admin = User(user_id=99, email="admin@example.com", full_name="Admin", password_hash="pw", role="admin")
    cv = CvDocumentRecord(id=30, user_id=1, title="User 1 CV", template_id="minimalist_ats", color_theme="slate")
    db_session.add_all([user, admin, cv])
    db_session.commit()

    # Admin deleting another user's CV should succeed
    service.delete_cv(db_session, user_id=99, cv_id=30)
    assert db_session.get(CvDocumentRecord, 30) is None
