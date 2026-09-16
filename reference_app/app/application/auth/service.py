from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
import uuid

from ...domain.errors import AuthError, ConflictError
from ...domain.identity import (
    OtpRecord,
    generate_otp_code,
    normalize_email,
    validate_full_name,
    validate_password,
)
from ..common import ClockPort
from .commands import (
    GoogleAuthCommand,
    LoginCommand,
    RegisterCommand,
    SendOtpCommand,
    VerifyOtpCommand,
)
from .ports import (
    AuthUser,
    EmailSenderPort,
    GoogleTokenVerifierPort,
    OtpStorePort,
    PasswordHasherPort,
    TokenIssuerPort,
    UserRepositoryPort,
    to_auth_user,
)


@dataclass
class AuthService:
    users: UserRepositoryPort
    hasher: PasswordHasherPort
    tokens: TokenIssuerPort
    clock: ClockPort | None = None
    otp_store: OtpStorePort | None = None
    email_sender: EmailSenderPort | None = None
    google_verifier: GoogleTokenVerifierPort | None = None

    def register(self, session: Any, command: RegisterCommand) -> AuthUser:
        full_name = validate_full_name(command.full_name)
        email = normalize_email(command.email)
        validate_password(command.password)
        if command.otp is not None:
            self.verify_otp(
                VerifyOtpCommand(
                    email=email, otp=command.otp, purpose="verify_email",
                ),
            )
        if self.users.find_by_email(session, email) is not None:
            raise ConflictError("email already registered")
        stored = self.users.add(
            session,
            full_name=full_name,
            email=email,
            password_hash=self.hasher.hash(command.password),
        )
        return to_auth_user(stored)

    def login(self, session: Any, command: LoginCommand) -> tuple[str, AuthUser]:
        email = normalize_email(command.email)
        stored = self.users.find_by_email(session, email)
        if stored is None or not self.hasher.verify(command.password, stored.password_hash):
            raise AuthError("invalid email or password")
        return self.tokens.issue(stored.user_id), to_auth_user(stored)

    def get_user(self, session: Any, user_id: int) -> AuthUser:
        stored = self.users.find_by_id(session, user_id)
        if stored is None:
            raise AuthError("invalid token")
        return to_auth_user(stored)

    def send_otp(self, command: SendOtpCommand) -> None:
        if self.otp_store is None or self.email_sender is None or self.clock is None:
            raise RuntimeError("OTP services not configured")
        email = normalize_email(command.email)
        code = generate_otp_code(6)
        expires_at = self.clock.now() + timedelta(minutes=10)
        record = OtpRecord(
            email=email,
            code=code,
            expires_at=expires_at,
            purpose=command.purpose,
        )
        self.otp_store.save(record)
        self.email_sender.send_otp_email(
            to_email=email,
            otp_code=code,
            purpose=command.purpose,
        )

    def verify_otp(self, command: VerifyOtpCommand) -> bool:
        if self.otp_store is None or self.clock is None:
            raise RuntimeError("OTP services not configured")
        email = normalize_email(command.email)
        record = self.otp_store.find(email, command.purpose)
        if record is None or not record.is_valid(command.otp, self.clock.now(), command.purpose):
            raise AuthError("invalid or expired OTP")
        self.otp_store.delete(email, command.purpose)
        return True

    def google_auth(self, session: Any, command: GoogleAuthCommand) -> tuple[str, AuthUser]:
        if self.google_verifier is None:
            raise RuntimeError("Google OAuth service not configured")
        profile = self.google_verifier.verify(command.credential)
        email = normalize_email(profile.email)
        stored = self.users.find_by_email(session, email)
        if stored is None:
            name = validate_full_name(profile.full_name or email.partition("@")[0])
            random_password = f"google-oauth-{uuid.uuid4().hex}"
            stored = self.users.add(
                session,
                full_name=name,
                email=email,
                password_hash=self.hasher.hash(random_password),
            )
        return self.tokens.issue(stored.user_id), to_auth_user(stored)
