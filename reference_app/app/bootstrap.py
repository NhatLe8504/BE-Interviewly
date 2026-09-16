from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from .application.admin.service import AdminService
from .application.analytics.service import AnalyticsService
from .application.audit.service import AuditLogService
from .application.auth.service import AuthService
from .application.billing.service import PaymentService, SubscriptionService
from .application.catalog.service import CatalogService
from .application.common import ClockPort
from .application.container import ServiceContainer
from .application.evaluation.service import EvaluationService
from .application.interview.service import InterviewService
from .application.profile.service import ProfileService
from .application.report.service import PdfReportService
from .application.speech.service import SpeechQualityService
from .config import Settings
from .infrastructure.clock import SystemClock
from .infrastructure.database import create_engine_from_url
from .infrastructure.email import SendGridEmailSender
from .infrastructure.llm.openai_adapter import OpenAILLMAdapter
from .infrastructure.oauth import GoogleOAuthAdapter
from .infrastructure.orm import Base, create_session_factory
from .infrastructure.otp import MemoryOtpStore
from .infrastructure.payment.stripe_adapter import StripeAdapter
from .infrastructure.payment.vnpay_adapter import VNPayAdapter
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
    catalog_service = CatalogService(
        repo=SqlAlchemyCatalogRepository(),
    )
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

    vnpay = VNPayAdapter(
        tmn_code=settings.vnpay_tmn_code,
        hash_secret=settings.vnpay_hash_secret,
        payment_url=settings.vnpay_payment_url,
        return_url=settings.vnpay_return_url,
    )
    stripe = StripeAdapter(
        api_key=settings.stripe_api_key,
        webhook_secret=settings.stripe_webhook_secret,
    )
    payment_service = PaymentService(
        subscription_repo=billing_repo,
        transaction_repo=billing_repo,
        gateways={"vnpay": vnpay, "stripe": stripe},
        clock=effective_clock,
        audit_service=audit_service,
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
    )
