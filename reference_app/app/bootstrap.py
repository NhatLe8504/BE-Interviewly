from __future__ import annotations

from .application.auth.service import AuthService
from .application.common import ClockPort
from .application.container import ServiceContainer
from .application.evaluation.service import EvaluationService
from .application.interview.service import InterviewService
from .application.speech.service import SpeechQualityService
from .config import Settings
from .infrastructure.clock import SystemClock
from .infrastructure.database import create_engine_from_url
from .infrastructure.email import SendGridEmailSender
from .infrastructure.llm.openai_adapter import OpenAILLMAdapter
from .infrastructure.oauth import GoogleOAuthAdapter
from .infrastructure.orm import Base, create_session_factory
from .infrastructure.otp import MemoryOtpStore
from .infrastructure.persistence import models as _models
from .infrastructure.persistence.evaluation_repository import SqlAlchemyEvaluationRepository
from .infrastructure.persistence.session_repository import SqlAlchemySessionRepository
from .infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from .infrastructure.security import JwtTokenService, Pbkdf2PasswordHasher
from .infrastructure.speech.text_analyzer import RegexSpeechTextAnalyzer


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

    return ServiceContainer(
        clock=effective_clock,
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        auth_service=auth_service,
        interview_service=interview_service,
        evaluation_service=evaluation_service,
        speech_service=speech_service,
    )
