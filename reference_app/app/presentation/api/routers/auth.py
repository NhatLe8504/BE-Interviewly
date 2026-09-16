from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ....application.auth.commands import (
    GoogleAuthCommand,
    LoginCommand,
    RegisterCommand,
    SendOtpCommand,
    VerifyOtpCommand,
)
from ....application.auth.ports import AuthUser
from ....application.container import ServiceContainer
from ....domain.errors import AuthError
from ..dependencies import get_container, get_session
from ..schemas.auth import (
    GoogleAuthIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    SendOtpIn,
    TokenOut,
    UserOut,
    VerifyOtpIn,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def _to_out(user: AuthUser) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        status=user.status,
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
    return _to_out(user)


@router.post("/login", response_model=TokenOut)
def login(
    data: LoginIn,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> TokenOut:
    token, _ = container.auth_service.login(
        session,
        LoginCommand(email=data.email, password=data.password),
    )
    return TokenOut(access_token=token)


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
    token, _ = container.auth_service.google_auth(
        session,
        GoogleAuthCommand(credential=data.credential),
    )
    return TokenOut(access_token=token)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserOut:
    if credentials is None or not credentials.credentials:
        raise AuthError("missing bearer token")
    user_id = container.auth_service.tokens.parse(credentials.credentials)
    return _to_out(container.auth_service.get_user(session, user_id))


@router.get("/me", response_model=UserOut)
def me(current: UserOut = Depends(get_current_user)) -> UserOut:
    return current
