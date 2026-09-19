from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ....application.auth.commands import (
    GoogleAuthCommand,
    LoginCommand,
    RegisterCommand,
    SendOtpCommand,
    VerifyOtpCommand,
)
from ....application.auth.ports import AuthUser
from ....application.container import ServiceContainer
from sqlalchemy import select
from ....domain.errors import NotFoundError
from ....infrastructure.persistence.models.onboarding import OnboardingResponse
from ....infrastructure.persistence.models.user import User
from ..dependencies import (
    bearer_scheme,
    get_container,
    get_current_user,
    get_current_user_id,
    get_session,
)
from ..schemas.auth import (
    GoogleAuthIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    SendOtpIn,
    SetInitialPasswordIn,
    TokenOut,
    UserOut,
    VerifyOtpIn,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _to_out(user: AuthUser, session: Any = None) -> UserOut:
    is_onboarded = False
    needs_password = False
    if session is not None:
        onboarding = session.execute(
            select(OnboardingResponse).where(OnboardingResponse.user_id == user.user_id)
        ).scalar_one_or_none()
        is_onboarded = bool(onboarding and onboarding.is_completed)

        user_row = session.execute(
            select(User).where(User.user_id == user.user_id)
        ).scalar_one_or_none()
        if user_row and user_row.password_hash and user_row.password_hash.startswith("needs_setup:"):
            needs_password = True

    return UserOut(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        status=user.status,
        is_onboarded=is_onboarded,
        needs_password=needs_password,
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    data: RegisterIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserOut:
    user = container.auth_service.register(
        session,
        RegisterCommand(
            full_name=data.full_name,
            email=data.email,
            password=data.password,
            otp=data.otp,
        ),
    )
    return _to_out(user, session)


@router.post("/login", response_model=TokenOut)
def login(
    data: LoginIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> TokenOut:
    token, auth_user = container.auth_service.login(
        session,
        LoginCommand(email=data.email, password=data.password),
    )
    onboarding = session.execute(
        select(OnboardingResponse).where(OnboardingResponse.user_id == auth_user.user_id)
    ).scalar_one_or_none()
    is_onboarded = bool(onboarding and onboarding.is_completed)

    user_row = session.execute(
        select(User).where(User.user_id == auth_user.user_id)
    ).scalar_one_or_none()
    needs_password = bool(
        user_row
        and user_row.password_hash
        and user_row.password_hash.startswith("needs_setup:")
    )

    return TokenOut(
        access_token=token,
        is_onboarded=is_onboarded,
        needs_password=needs_password,
    )


@router.post("/send-otp", response_model=MessageOut)
def send_otp(
    data: SendOtpIn,
    container: ServiceContainer = Depends(get_container),
) -> MessageOut:
    container.auth_service.send_otp(
        SendOtpCommand(email=data.email, purpose=data.purpose),
    )
    return MessageOut(message="OTP sent successfully")


@router.post("/verify-otp", response_model=MessageOut)
def verify_otp(
    data: VerifyOtpIn,
    container: ServiceContainer = Depends(get_container),
) -> MessageOut:
    container.auth_service.verify_otp(
        VerifyOtpCommand(email=data.email, otp=data.otp, purpose=data.purpose),
    )
    return MessageOut(message="OTP verified successfully")


@router.post("/google", response_model=TokenOut)
def google_auth(
    data: GoogleAuthIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> TokenOut:
    token, auth_user, is_new_user = container.auth_service.google_auth(
        session,
        GoogleAuthCommand(credential=data.credential),
    )
    onboarding = session.execute(
        select(OnboardingResponse).where(OnboardingResponse.user_id == auth_user.user_id)
    ).scalar_one_or_none()
    is_onboarded = bool(onboarding and onboarding.is_completed)

    user_row = session.execute(
        select(User).where(User.user_id == auth_user.user_id)
    ).scalar_one_or_none()
    needs_password = is_new_user or bool(
        user_row
        and user_row.password_hash
        and user_row.password_hash.startswith("needs_setup:")
    )

    return TokenOut(
        access_token=token,
        is_new_user=is_new_user,
        needs_password=needs_password,
        is_onboarded=is_onboarded,
    )


@router.get("/me", response_model=UserOut)
def me(
    current: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
) -> UserOut:
    return _to_out(current, session)


@router.post("/set-initial-password", response_model=MessageOut)
def set_initial_password(
    data: SetInitialPasswordIn,
    current_user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> MessageOut:
    """Set the initial password for users who logged in via Google without a password."""
    user_row = session.execute(
        select(User).where(User.user_id == current_user_id)
    ).scalar_one_or_none()
    if not user_row:
        raise NotFoundError("User not found")

    user_row.password_hash = container.auth_service.hasher.hash(data.password)
    session.commit()
    return MessageOut(message="Thiết lập mật khẩu tài khoản thành công!")
