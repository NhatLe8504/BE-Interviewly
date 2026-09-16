from __future__ import annotations

from .application.analytics.service import AnalyticsService
from .application.auth.service import AuthService
from .application.common import ClockPort
from .application.container import ServiceContainer
from .config import Settings
from .infrastructure.clock import SystemClock
from .infrastructure.database import create_engine_from_url
from .infrastructure.email import SendGridEmailSender
from .infrastructure.oauth import GoogleOAuthAdapter
from .infrastructure.orm import Base, create_session_factory
from .infrastructure.otp import MemoryOtpStore
from .infrastructure.persistence import models as _models
from .infrastructure.persistence.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from .infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from .infrastructure.security import JwtTokenService, Pbkdf2PasswordHasher


def build_services(
    clock: ClockPort | None = None,
    settings: Settings | None = None,
) -> ServiceContainer:
    settings = settings or Settings.from_env()
    effective_clock = clock or SystemClock()
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(engine)
    auth_service = AuthService(
        users=SqlAlchemyUserRepository(),
        hasher=Pbkdf2PasswordHasher(),
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
    analytics_service = AnalyticsService(
        repo=SqlAlchemyAnalyticsRepository(),
    )
    return ServiceContainer(
        clock=effective_clock,
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        auth_service=auth_service,
        analytics_service=analytics_service,
    )
