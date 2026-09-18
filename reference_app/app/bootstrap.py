from __future__ import annotations

def _auto_migrate_columns(engine: Any) -> None:
    """Ensures newly added columns exist in existing PostgreSQL/SQLite tables."""
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
            ]
            for col_name, col_def in cols:
                conn.exec_driver_sql(f"ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
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
from .infrastructure.storage.cloudinary_storage import CloudinaryStorageService


def _seed_subscription_plans(session_factory: Any) -> None:
    session = session_factory()
    try:
        count = session.execute(select(func.count(OrmSubscriptionPlan.plan_id))).scalar()
        if count == 0:
            free = OrmSubscriptionPlan(
                plan_name="Free",
                price=Decimal("0"),
                billing_cycle=BillingCycle.free,
                feature_limits={"interview_turns": 5, "ai_feedback": "basic"},
                is_active=True,
            )
            monthly = OrmSubscriptionPlan(
                plan_name="Pro Monthly",
                price=Decimal("99000"),
                billing_cycle=BillingCycle.monthly,
                feature_limits={"interview_turns": 100, "ai_feedback": "detailed", "pdf_reports": True},
                is_active=True,
            )
            yearly = OrmSubscriptionPlan(
                plan_name="Pro Yearly",
                price=Decimal("899000"),
                billing_cycle=BillingCycle.yearly,
                feature_limits={"interview_turns": 1500, "ai_feedback": "detailed", "pdf_reports": True},
                is_active=True,
            )
            session.add_all([free, monthly, yearly])
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
    _auto_migrate_columns(engine)
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


    # Edge TTS
    tts_adapter = EdgeTTSAdapter()

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
    )

