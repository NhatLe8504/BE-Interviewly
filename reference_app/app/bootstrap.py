from __future__ import annotations

def _auto_migrate_columns(engine: Any) -> None:
    """Ensures newly added columns exist in existing PostgreSQL/SQLite tables."""
    from .infrastructure.persistence.job_metadata_migration import migrate_job_metadata

    migrate_job_metadata(engine)
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            # Create enums if not exist
            conn.exec_driver_sql("""
                DO $$ BEGIN
                    CREATE TYPE question_moderation_status_enum AS ENUM ('pending', 'approved', 'rejected');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
                DO $$ BEGIN
                    CREATE TYPE question_source_enum AS ENUM ('admin_manual', 'admin_ai', 'user_ai', 'user_manual');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """)
            # Alter question_bank columns
            cols = [
                ("moderation_status", "question_moderation_status_enum DEFAULT 'approved' NOT NULL"),
                ("moderated_by", "BIGINT"),
                ("moderated_at", "TIMESTAMP WITH TIME ZONE"),
                ("moderation_reason", "TEXT"),
                ("source", "question_source_enum DEFAULT 'admin_manual' NOT NULL"),
                ("practice_id", "BIGINT"),
                ("intent", "TEXT"),
                ("difficulty", "INTEGER DEFAULT 3"),
                ("skill_ids", "JSON DEFAULT '[]'"),
                ("skill_ids", "JSON DEFAULT '[]'::json"),
            ]
            for col_name, col_def in cols:
                conn.exec_driver_sql(f"ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
            for table_name, col_name, col_def in [
                ("star_guidance_templates", "is_active", "BOOLEAN DEFAULT TRUE NOT NULL"),
                ("answer_evaluations", "question_type", "VARCHAR(20)"),
                ("answer_evaluations", "rubric_version", "INTEGER DEFAULT 1 NOT NULL"),
                ("jd_generation_jobs", "request_payload", "JSON"),
                ("jd_generation_jobs", "notification_pending", "BOOLEAN DEFAULT FALSE NOT NULL"),
                ("job_domains", "is_active", "BOOLEAN DEFAULT TRUE NOT NULL"),
                ("job_roles", "is_active", "BOOLEAN DEFAULT TRUE NOT NULL"),
                ("candidate_profiles", "mascot_id", "VARCHAR(32) DEFAULT 'fox-pixel' NOT NULL"),
                ("job_readiness_checks", "analysis_engine", "VARCHAR(16) DEFAULT 'heuristic' NOT NULL"),
            ]:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_def};"
                )
            conn.exec_driver_sql(
                "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS barge_in_enabled BOOLEAN DEFAULT FALSE NOT NULL;"
            )
        elif dialect == "sqlite":
            for col_name, col_def in [
                ("moderation_status", "VARCHAR DEFAULT 'approved'"),
                ("moderated_by", "BIGINT"),
                ("moderated_at", "DATETIME"),
                ("moderation_reason", "TEXT"),
                ("source", "VARCHAR DEFAULT 'admin_manual'"),
                ("practice_id", "BIGINT"),
                ("intent", "TEXT"),
                ("difficulty", "INTEGER DEFAULT 3"),
            ]:
                try:
                    conn.exec_driver_sql(f"ALTER TABLE question_bank ADD COLUMN {col_name} {col_def};")
                except Exception:
                    pass
            for table_name, col_name, col_def in [
                ("star_guidance_templates", "is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
                ("answer_evaluations", "question_type", "VARCHAR(20)"),
                ("answer_evaluations", "rubric_version", "INTEGER DEFAULT 1 NOT NULL"),
                ("jd_generation_jobs", "request_payload", "JSON"),
                ("jd_generation_jobs", "notification_pending", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("job_domains", "is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
                ("job_roles", "is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
                ("candidate_profiles", "mascot_id", "VARCHAR(32) DEFAULT 'fox-pixel' NOT NULL"),
                ("job_readiness_checks", "analysis_engine", "VARCHAR(16) DEFAULT 'heuristic' NOT NULL"),
            ]:
                try:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};")
                except Exception:
                    pass
            try:
                conn.exec_driver_sql(
                    "ALTER TABLE interview_sessions ADD COLUMN barge_in_enabled BOOLEAN DEFAULT 0 NOT NULL;"
                )
            except Exception:
                pass


from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from .application.admin.service import AdminService
from .application.analytics.service import AnalyticsService
from .application.audit.service import AuditLogService
from .application.auth.service import AuthService
from .application.billing.service import PaymentService, SubscriptionService
from .application.cache.service import CacheService
from .application.catalog.service import CatalogService
from .application.common import ClockPort
from .application.container import ServiceContainer
from .application.cv.service import CvService
from .application.evaluation.service import EvaluationService
from .application.interview.service import InterviewService
from .application.profile.service import ProfileService
from .application.report.service import PdfReportService
from .application.speech.service import SpeechQualityService
from .config import Settings
from .infrastructure.cache.redis_cache import MemoryCacheAdapter, RedisCacheAdapter
from .infrastructure.clock import SystemClock
from .infrastructure.database import create_engine_from_url
from .infrastructure.email import SendGridEmailSender
from .infrastructure.llm.openai_adapter import OpenAILLMAdapter
from .infrastructure.oauth import GoogleOAuthAdapter
from .infrastructure.orm import Base, create_session_factory
from .infrastructure.otp import MemoryOtpStore
from .infrastructure.payment.xgate_adapter import XGateAdapter
from .infrastructure.persistence import models as _models
from .infrastructure.persistence.admin_repository import (
    SqlAlchemyAdminRepository,
)
from .infrastructure.persistence.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from .infrastructure.persistence.audit_repository import SqlAlchemyAuditRepository
from .infrastructure.persistence.billing_repository import SqlAlchemyBillingRepository
from .infrastructure.persistence.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from .infrastructure.persistence.evaluation_repository import SqlAlchemyEvaluationRepository
from .infrastructure.persistence.models.billing import SubscriptionPlan as OrmSubscriptionPlan
from .infrastructure.persistence.models.enums import BillingCycle
from .infrastructure.persistence.profile_repository import (
    SqlAlchemyProfileRepository,
)
from .infrastructure.persistence.session_report_repository import SqlAlchemySessionReportRepository
from .infrastructure.persistence.session_repository import SqlAlchemySessionRepository
from .infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from .infrastructure.redis_client import create_redis_client
from .infrastructure.report.reportlab_pdf import ReportLabPdfGenerator
from .infrastructure.security import JwtTokenService, Pbkdf2PasswordHasher
from .infrastructure.speech.text_analyzer import RegexSpeechTextAnalyzer
from .infrastructure.tts.edge_tts_adapter import EdgeTTSAdapter
from .infrastructure.tts.elevenlabs_adapter import ElevenLabsTTSAdapter
from .infrastructure.tts.vieneu_adapter import VieNeuTTSAdapter
from .infrastructure.storage.cloudinary_storage import CloudinaryStorageService


DEFAULT_SUBSCRIPTION_PLANS = [
    {
        "plan_id": 1,
        "plan_name": "Free",
        "price": Decimal("0"),
        "billing_cycle": BillingCycle.free,
        "feature_limits": {
            "type": "subscription",
            "voice_minutes": 15,
            "cv_generations": 1,
            "interview_turns": 15,
            "ai_feedback": "basic",
        },
        "is_active": True,
    },
    {
        "plan_id": 2,
        "plan_name": "Pro Monthly",
        "price": Decimal("99000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "subscription",
            "voice_minutes": 300,
            "cv_generations": 15,
            "interview_turns": 300,
            "ai_feedback": "detailed",
            "pdf_reports": True,
        },
        "is_active": True,
    },
    {
        "plan_id": 3,
        "plan_name": "Pro Yearly",
        "price": Decimal("899000"),
        "billing_cycle": BillingCycle.yearly,
        "feature_limits": {
            "type": "subscription",
            "voice_minutes": 4000,
            "cv_generations": 200,
            "interview_turns": 4000,
            "ai_feedback": "detailed",
            "pdf_reports": True,
        },
        "is_active": True,
    },
    {
        "plan_id": 4,
        "plan_name": "Sprint 7 Ngày (Cấp Tốc)",
        "price": Decimal("49000"),
        "billing_cycle": BillingCycle.weekly,
        "feature_limits": {
            "type": "subscription",
            "voice_minutes": 60,
            "cv_generations": 3,
            "interview_turns": 60,
            "ai_feedback": "detailed",
            "pdf_reports": True,
            "speech_analysis": True,
        },
        "is_active": True,
    },
    {
        "plan_id": 101,
        "plan_name": "Add-on Voice 30m",
        "price": Decimal("29000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "addon",
            "addon_type": "voice",
            "voice_minutes": 30,
        },
        "is_active": True,
    },
    {
        "plan_id": 102,
        "plan_name": "Add-on Voice 60m",
        "price": Decimal("49000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "addon",
            "addon_type": "voice",
            "voice_minutes": 60,
        },
        "is_active": True,
    },
    {
        "plan_id": 103,
        "plan_name": "Add-on Voice 120m",
        "price": Decimal("89000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "addon",
            "addon_type": "voice",
            "voice_minutes": 120,
        },
        "is_active": True,
    },
    {
        "plan_id": 104,
        "plan_name": "Add-on CV 3x",
        "price": Decimal("19000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "addon",
            "addon_type": "cv",
            "cv_generations": 3,
        },
        "is_active": True,
    },
    {
        "plan_id": 105,
        "plan_name": "Add-on CV 10x",
        "price": Decimal("49000"),
        "billing_cycle": BillingCycle.monthly,
        "feature_limits": {
            "type": "addon",
            "addon_type": "cv",
            "cv_generations": 10,
        },
        "is_active": True,
    },
]


def _seed_subscription_plans(session_factory: Any) -> None:
    session = session_factory()
    try:
        for plan_spec in DEFAULT_SUBSCRIPTION_PLANS:
            # Check by plan_id first or plan_name
            existing = session.get(OrmSubscriptionPlan, plan_spec["plan_id"])
            if not existing:
                existing = session.execute(
                    select(OrmSubscriptionPlan).where(OrmSubscriptionPlan.plan_name == plan_spec["plan_name"])
                ).scalar_one_or_none()

            if existing:
                existing.price = plan_spec["price"]
                existing.billing_cycle = plan_spec["billing_cycle"]
                existing.feature_limits = plan_spec["feature_limits"]
                existing.is_active = plan_spec["is_active"]
            else:
                new_plan = OrmSubscriptionPlan(
                    plan_id=plan_spec["plan_id"],
                    plan_name=plan_spec["plan_name"],
                    price=plan_spec["price"],
                    billing_cycle=plan_spec["billing_cycle"],
                    feature_limits=plan_spec["feature_limits"],
                    is_active=plan_spec["is_active"],
                )
                session.add(new_plan)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def build_services(
    clock: ClockPort | None = None,
    settings: Settings | None = None,
) -> ServiceContainer:
    settings = settings or Settings.from_env()
    effective_clock = clock or SystemClock()
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(engine)
    try:
        _auto_migrate_columns(engine)
    except Exception:
        pass
    session_factory = create_session_factory(engine)
    _seed_subscription_plans(session_factory)
    hasher = Pbkdf2PasswordHasher()

    # Auth
    auth_service = AuthService(
        users=SqlAlchemyUserRepository(),
        hasher=hasher,
        tokens=JwtTokenService(
            secret=settings.jwt_secret,
            expires_minutes=settings.jwt_expires_minutes,
        ),
        clock=effective_clock,
        otp_store=MemoryOtpStore(),
        email_sender=SendGridEmailSender(
            api_key=settings.sendgrid_api_key,
            from_email=settings.sendgrid_from_email,
            from_name=settings.sendgrid_from_name,
        ),
        google_verifier=GoogleOAuthAdapter(
            client_id=settings.google_client_id,
        ),
    )

    profile_service = ProfileService(
        repo=SqlAlchemyProfileRepository(),
        hasher=hasher,
    )
    catalog_repo = SqlAlchemyCatalogRepository()
    catalog_service = CatalogService(repo=catalog_repo)
    admin_service = AdminService(
        repo=SqlAlchemyAdminRepository(),
    )

    # Analytics
    analytics_service = AnalyticsService(
        repo=SqlAlchemyAnalyticsRepository(),
    )

    # AI Engine
    llm_adapter = OpenAILLMAdapter(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
    )
    session_repo = SqlAlchemySessionRepository()
    eval_repo = SqlAlchemyEvaluationRepository()
    speech_analyzer = RegexSpeechTextAnalyzer()

    interview_service = InterviewService(
        sessions=session_repo,
        turns=session_repo,
        llm=llm_adapter,
        clock=effective_clock,
        questions=catalog_repo,
    )
    evaluation_service = EvaluationService(
        evaluations=eval_repo,
        evaluator=llm_adapter,
        clock=effective_clock,
    )
    speech_service = SpeechQualityService(
        analyzer=speech_analyzer,
    )

    # Billing & Audit
    audit_repo = SqlAlchemyAuditRepository()
    audit_service = AuditLogService(audit_repo=audit_repo)

    billing_repo = SqlAlchemyBillingRepository()
    subscription_service = SubscriptionService(
        subscription_repo=billing_repo,
        clock=effective_clock,
    )

    xgate = XGateAdapter(
        api_key=settings.xgate_api_key,
        api_url=settings.xgate_api_url,
        receiver_bank=settings.xgate_receiver_bank,
        receiver_account=settings.xgate_receiver_account,
        receiver_name=settings.xgate_receiver_name,
    )
    payment_service = PaymentService(
        subscription_repo=billing_repo,
        transaction_repo=billing_repo,
        xgate_gateway=xgate,
        clock=effective_clock,
        audit_service=audit_service,
        gateways={"xgate": xgate},
    )

    # Report
    storage_dir = Path(__file__).resolve().parents[1] / settings.pdf_reports_dir
    session_report_repo = SqlAlchemySessionReportRepository()
    pdf_report_service = PdfReportService(
        generator=ReportLabPdfGenerator(),
        repo=session_report_repo,
        storage_dir=storage_dir,
    )

    # Redis Client
    try:
        redis_client = create_redis_client(settings.redis_url)
    except Exception:
        redis_client = None

    # Cloudinary Storage
    storage_service = CloudinaryStorageService(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        cloudinary_url=settings.cloudinary_url,
    )

    # Cache Service
    cache_adapter = RedisCacheAdapter(redis_client) if redis_client is not None else MemoryCacheAdapter()
    cache_service = CacheService(cache=cache_adapter)


    edge_tts = EdgeTTSAdapter()
    eleven_key = getattr(settings, "elevenlabs_api_key", "")
    tts_adapter = VieNeuTTSAdapter(api_key=settings.vieneu_api_key, fallback=edge_tts)

    # Automated Job Ingestion Worker
    from .application.job_aggregator.worker import JobIngestionWorker
    from .infrastructure.company_branding import SerperCompanyBrandingLookup
    serper_key = getattr(settings, "serper_api_key", "")
    branding_lookup = SerperCompanyBrandingLookup(
        api_key=serper_key,
        redis_client=redis_client,
    ) if serper_key else None
    job_worker = JobIngestionWorker(
        session_factory=session_factory,
        redis_client=redis_client,
        serper_api_key=serper_key,
        crawl_interval_seconds=3600,
        branding_lookup=branding_lookup,
    )

    # CV Builder Service
    cv_service = CvService(
        llm=llm_adapter,
        clock=effective_clock,
    )

    # Course Management Service
    from .infrastructure.persistence.course_repository import CourseRepository
    from .application.course.service import CourseService
    course_repo = CourseRepository()
    course_service = CourseService(repo=course_repo)

    return ServiceContainer(
        clock=effective_clock,
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        auth_service=auth_service,
        profile_service=profile_service,
        catalog_service=catalog_service,
        admin_service=admin_service,
        interview_service=interview_service,
        evaluation_service=evaluation_service,
        speech_service=speech_service,
        subscription_service=subscription_service,
        payment_service=payment_service,
        audit_service=audit_service,
        pdf_report_service=pdf_report_service,
        analytics_service=analytics_service,
        redis_client=redis_client,
        storage_service=storage_service,
        cache_service=cache_service,
        tts_adapter=tts_adapter,
        llm_voice_adapter=llm_adapter,
        job_worker=job_worker,
        cv_service=cv_service,
        course_service=course_service,
    )


