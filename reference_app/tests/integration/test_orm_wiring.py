from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text

from app.bootstrap import build_services
from app.config import DEFAULT_DATABASE_URL, Settings
from app.infrastructure.orm import Base, create_session_factory

EXPECTED_TABLES = {
    "users",
    "candidate_profiles",
    "job_domains",
    "job_roles",
    "star_guidance_templates",
    "question_bank",
    "interview_sessions",
    "interview_turns",
    "answer_evaluations",
    "speech_quality_analysis",
    "session_progress_summary",
    "pdf_reports",
    "subscription_plans",
    "user_subscriptions",
    "payment_transactions",
    "moderation_logs",
    "audit_logs",
}


def test_models_registered_on_base_metadata() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_session_factory_opens_and_closes_session() -> None:
    engine = create_engine("sqlite://")
    factory = create_session_factory(engine)
    session = factory()
    try:
        assert session.execute(text("SELECT 1")).scalar() == 1
    finally:
        session.close()


def test_container_wires_engine_and_session_factory() -> None:
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    probe = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        with probe.connect():
            pass
    except Exception:
        pytest.skip("postgres not reachable")
    container = build_services(settings=Settings(database_url=url))
    assert container.engine is not None
    assert container.session_factory is not None
    assert container.settings.database_url == url


def test_create_all_autocreates_tables_on_postgres() -> None:
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        with engine.connect():
            pass
    except Exception:
        pytest.skip("postgres not reachable")
    Base.metadata.create_all(engine)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
