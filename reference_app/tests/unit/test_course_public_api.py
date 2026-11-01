from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

from app.application.course.service import CourseService
from app.infrastructure.orm import Base
from app.infrastructure.persistence.course_repository import CourseRepository
from datetime import datetime, timezone
from decimal import Decimal
from app.infrastructure.persistence.models.billing import (
    BillingCycle,
    SubscriptionPlan,
    SubStatus,
    UserSubscription,
)
from app.infrastructure.persistence.models.course import Course, CourseChapter, CourseLesson
from app.infrastructure.persistence.models.user import User
from app.presentation.api.routers.course import (
    _to_course_detail_out,
    get_course_detail,
    get_lesson_detail,
    list_courses,
    sanitize_course_html,
    sanitize_media_url,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            UserSubscription.__table__,
            SubscriptionPlan.__table__,
            Course.__table__,
            CourseChapter.__table__,
            CourseLesson.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def _seed_course_data(session: Session):
    # Free candidate user
    free_user = User(user_id=1, email="free@example.com", full_name="Free User", password_hash="pw", role="candidate")
    # Pro subscriber user
    pro_user = User(user_id=2, email="pro@example.com", full_name="Pro User", password_hash="pw", role="candidate")
    # Admin user
    admin_user = User(user_id=3, email="admin@example.com", full_name="Admin User", password_hash="pw", role="admin")

    plan = SubscriptionPlan(
        plan_id=1,
        plan_name="Pro Monthly",
        price=Decimal("199000.00"),
        billing_cycle=BillingCycle.monthly,
        feature_limits={},
        is_active=True,
    )
    sub = UserSubscription(
        user_subscription_id=1,
        user_id=2,
        plan_id=1,
        status=SubStatus.active,
        start_date=datetime.now(timezone.utc),
        plan=plan,
    )

    session.add_all([free_user, pro_user, admin_user, plan, sub])
    session.commit()

    # Active Course 1
    c1 = Course(
        course_id=1,
        title="System Design Mastery",
        slug="system-design-mastery",
        type="course",
        category="system_design",
        role="Software Engineer",
        level="senior",
        estimated_hours=20,
        description="Comprehensive system design prep",
        is_active=True,
    )
    session.add(c1)
    session.commit()

    ch1 = CourseChapter(chapter_id=10, course_id=1, title="Fundamentals", order_index=1)
    session.add(ch1)
    session.commit()

    ls1_free = CourseLesson(
        lesson_id=101,
        chapter_id=10,
        title="Intro to Scalability",
        duration_minutes=15,
        type="video",
        is_free=True,
        order_index=1,
        video_url="https://video.example.com/intro.mp4",
        content_html="<p>Introduction text</p>",
    )
    ls2_locked = CourseLesson(
        lesson_id=102,
        chapter_id=10,
        title="Distributed Caching Architecture",
        duration_minutes=25,
        type="star_practice",
        is_free=False,
        order_index=2,
        video_url="https://video.example.com/caching.mp4",
        content_html="<p>Deep caching guide</p>",
        practice_question={"title": "Design a Distributed Cache"},
    )
    session.add_all([ls1_free, ls2_locked])
    session.commit()

    # Inactive Course 2
    c2_inactive = Course(
        course_id=2,
        title="Hidden Draft Course",
        slug="hidden-draft",
        type="workshop",
        category="swe",
        level="junior",
        is_active=False,
    )
    session.add(c2_inactive)
    session.commit()

    ch2 = CourseChapter(chapter_id=20, course_id=2, title="Draft Chapter", order_index=1)
    session.add(ch2)
    session.commit()
    ls3_inactive = CourseLesson(
        lesson_id=201,
        chapter_id=20,
        title="Draft Lesson",
        is_free=True,
        order_index=1,
    )
    session.add(ls3_inactive)
    session.commit()


def test_sanitize_course_html():
    dirty = '<p>Safe text</p><script>alert("xss")</script><iframe src="malicious.html"></iframe><img src="pic.jpg" onerror="steal()">'
    clean = sanitize_course_html(dirty)
    assert clean is not None
    assert "alert" not in clean
    assert "script" not in clean
    assert "iframe" not in clean
    assert "onerror" not in clean
    assert "Safe text" in clean

    assert sanitize_course_html(None) is None
    assert sanitize_course_html("   ") is None


def test_sanitize_media_url():
    assert sanitize_media_url("https://example.com/video.mp4") == "https://example.com/video.mp4"
    assert sanitize_media_url("http://example.com/video.mp4") == "http://example.com/video.mp4"
    assert sanitize_media_url("/videos/lesson1.mp4") == "/videos/lesson1.mp4"
    assert sanitize_media_url("javascript:alert(1)") is None
    assert sanitize_media_url("data:text/html;base64,PHNjcmlwdD4=") is None
    assert sanitize_media_url(None) is None


def test_list_courses_filters_type_and_active(db_session: Session):
    _seed_course_data(db_session)
    container = MagicMock()
    repo = CourseRepository()
    from app.application.course.service import CourseService
    container.course_service = CourseService(repo)

    # 1. Public list returns only active courses
    res = list_courses(session=db_session, container=container)
    assert res["total"] == 1
    assert res["items"][0].slug == "system-design-mastery"

    # 2. Filter by type matching
    res_type = list_courses(type="course", session=db_session, container=container)
    assert res_type["total"] == 1

    # 3. Filter by type non-matching
    res_nomatch = list_courses(type="workshop", session=db_session, container=container)
    assert res_nomatch["total"] == 0


def test_get_course_detail_inactive_returns_404(db_session: Session):
    _seed_course_data(db_session)
    container = MagicMock()
    container.course_service = CourseService(CourseRepository())

    with pytest.raises(HTTPException) as exc_info:
        get_course_detail("hidden-draft", user_id=None, session=db_session, container=container)
    assert exc_info.value.status_code == 404


def test_get_course_detail_security_gate_g1(db_session: Session):
    _seed_course_data(db_session)
    container = MagicMock()
    container.course_service = CourseService(CourseRepository())

    # Guest user: locked lesson must be stripped of content
    detail_guest = get_course_detail("system-design-mastery", user_id=None, session=db_session, container=container)
    ch1 = detail_guest.chapters[0]
    ls1 = ch1.lessons[0]  # free
    ls2 = ch1.lessons[1]  # locked

    assert ls1.is_free is True
    assert ls1.content_html == "<p>Introduction text</p>"
    assert ls1.video_url == "https://video.example.com/intro.mp4"

    assert ls2.is_free is False
    assert ls2.content_html is None
    assert ls2.video_url is None
    assert ls2.practice_question is None

    # Free candidate user (not Pro): also stripped
    detail_free_user = get_course_detail("system-design-mastery", user_id=1, session=db_session, container=container)
    ls2_free = detail_free_user.chapters[0].lessons[1]
    assert ls2_free.content_html is None
    assert ls2_free.video_url is None

    # Pro user: full content unlocked
    detail_pro = get_course_detail("system-design-mastery", user_id=2, session=db_session, container=container)
    ls2_pro = detail_pro.chapters[0].lessons[1]
    assert ls2_pro.content_html == "<p>Deep caching guide</p>"
    assert ls2_pro.video_url == "https://video.example.com/caching.mp4"
    assert ls2_pro.practice_question == {"title": "Design a Distributed Cache"}


def test_get_lesson_detail_authorization_and_guards(db_session: Session):
    _seed_course_data(db_session)
    container = MagicMock()
    container.course_service = CourseService(CourseRepository())

    # 1. Lesson from inactive course -> 404
    with pytest.raises(HTTPException) as exc_info:
        get_lesson_detail("hidden-draft", lesson_id=201, user_id=None, session=db_session, container=container)
    assert exc_info.value.status_code == 404

    # 2. Non-existent lesson -> 404
    with pytest.raises(HTTPException) as exc_info:
        get_lesson_detail("system-design-mastery", lesson_id=9999, user_id=None, session=db_session, container=container)
    assert exc_info.value.status_code == 404

    # 3. Lesson belonging to different course -> 404
    with pytest.raises(HTTPException) as exc_info:
        get_lesson_detail("system-design-mastery", lesson_id=201, user_id=None, session=db_session, container=container)
    assert exc_info.value.status_code == 404

    # 4. Free lesson accessible to guest -> 200
    res_free = get_lesson_detail("system-design-mastery", lesson_id=101, user_id=None, session=db_session, container=container)
    assert res_free.lesson_id == 101
    assert res_free.content_html == "<p>Introduction text</p>"

    # 5. Locked lesson accessed by guest -> 401
    with pytest.raises(HTTPException) as exc_info:
        get_lesson_detail("system-design-mastery", lesson_id=102, user_id=None, session=db_session, container=container)
    assert exc_info.value.status_code == 401

    # 6. Locked lesson accessed by free user -> 403
    with pytest.raises(HTTPException) as exc_info:
        get_lesson_detail("system-design-mastery", lesson_id=102, user_id=1, session=db_session, container=container)
    assert exc_info.value.status_code == 403

    # 7. Locked lesson accessed by Pro user -> 200
    res_pro = get_lesson_detail("system-design-mastery", lesson_id=102, user_id=2, session=db_session, container=container)
    assert res_pro.lesson_id == 102
    assert res_pro.content_html == "<p>Deep caching guide</p>"

    # 8. Locked lesson accessed by Admin user -> 200
    res_admin = get_lesson_detail("system-design-mastery", lesson_id=102, user_id=3, session=db_session, container=container)
    assert res_admin.lesson_id == 102
    assert res_admin.content_html == "<p>Deep caching guide</p>"
