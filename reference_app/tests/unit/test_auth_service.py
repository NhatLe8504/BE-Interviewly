from __future__ import annotations

import pytest

from app.application.auth.commands import LoginCommand, RegisterCommand
from app.application.auth.ports import StoredUser
from app.application.auth.service import AuthService
from app.domain.errors import AuthError, ConflictError, DomainValidationError


class FakeUsers:
    def __init__(self) -> None:
        self.rows: dict[str, StoredUser] = {}
        self.next_id = 1

    def find_by_email(self, session, email: str):
        return self.rows.get(email)

    def find_by_id(self, session, user_id: int):
        for row in self.rows.values():
            if row.user_id == user_id:
                return row
        return None

    def add(self, session, *, full_name: str, email: str, password_hash: str):
        row = StoredUser(
            user_id=self.next_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role="candidate",
            status="active",
        )
        self.next_id += 1
        self.rows[email] = row
        return row


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeTokens:
    def issue(self, user_id: int) -> str:
        return f"token-{user_id}"

    def parse(self, token: str) -> int:
        return int(token.rsplit("-", 1)[1])


def make_service() -> AuthService:
    return AuthService(users=FakeUsers(), hasher=FakeHasher(), tokens=FakeTokens())


def test_register_ok() -> None:
    service = make_service()
    user = service.register(
        None, RegisterCommand("Test User", "User@Example.com ", "password123"),
    )
    assert user.email == "user@example.com"
    assert user.role == "candidate"


def test_register_duplicate_email_conflicts() -> None:
    service = make_service()
    command = RegisterCommand("Test User", "dup@example.com", "password123")
    service.register(None, command)
    with pytest.raises(ConflictError):
        service.register(None, command)


def test_register_rejects_bad_input() -> None:
    service = make_service()
    with pytest.raises(DomainValidationError):
        service.register(None, RegisterCommand("Test", "not-an-email", "password123"))
    with pytest.raises(DomainValidationError):
        service.register(None, RegisterCommand("Test", "ok@example.com", "short"))


def test_login_ok_and_wrong_password() -> None:
    service = make_service()
    service.register(None, RegisterCommand("Test", "login@example.com", "password123"))
    token, user = service.login(
        None, LoginCommand("login@example.com", "password123"),
    )
    assert token == f"token-{user.user_id}"
    with pytest.raises(AuthError):
        service.login(None, LoginCommand("login@example.com", "wrong-pass"))
    with pytest.raises(AuthError):
        service.login(None, LoginCommand("missing@example.com", "password123"))

from datetime import datetime, timezone
from app.application.auth.commands import (
    GoogleAuthCommand,
    SendOtpCommand,
    VerifyOtpCommand,
)
from app.application.auth.ports import GoogleProfile
from app.domain.identity import OtpRecord


class FakeClock:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, minutes: int) -> None:
        from datetime import timedelta
        self._now += timedelta(minutes=minutes)


class FakeOtpStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], OtpRecord] = {}

    def save(self, record: OtpRecord) -> None:
        self.records[(record.email, record.purpose)] = record

    def find(self, email: str, purpose: str = "verify_email") -> OtpRecord | None:
        return self.records.get((email, purpose))

    def delete(self, email: str, purpose: str = "verify_email") -> None:
        self.records.pop((email, purpose), None)


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_otp_email(self, to_email: str, otp_code: str, purpose: str = "verify_email") -> None:
        self.sent.append((to_email, otp_code, purpose))


class FakeGoogleVerifier:
    def __init__(self) -> None:
        self.profiles: dict[str, GoogleProfile] = {}

    def verify(self, credential: str) -> GoogleProfile:
        if credential not in self.profiles:
            raise AuthError("invalid google token")
        return self.profiles[credential]


def make_full_service():
    clock = FakeClock()
    otp_store = FakeOtpStore()
    email_sender = FakeEmailSender()
    google_verifier = FakeGoogleVerifier()
    service = AuthService(
        users=FakeUsers(),
        hasher=FakeHasher(),
        tokens=FakeTokens(),
        clock=clock,
        otp_store=otp_store,
        email_sender=email_sender,
        google_verifier=google_verifier,
    )
    return service, clock, otp_store, email_sender, google_verifier


def test_send_and_verify_otp_flow() -> None:
    service, clock, otp_store, email_sender, _ = make_full_service()
    service.send_otp(SendOtpCommand("test@example.com"))
    assert len(email_sender.sent) == 1
    email, otp_code, purpose = email_sender.sent[0]
    assert email == "test@example.com"
    assert len(otp_code) == 6

    # Verify wrong OTP raises AuthError
    with pytest.raises(AuthError):
        service.verify_otp(VerifyOtpCommand("test@example.com", "999999"))

    # Verify correct OTP succeeds
    assert service.verify_otp(VerifyOtpCommand("test@example.com", otp_code)) is True
    # Once consumed, second verify fails
    with pytest.raises(AuthError):
        service.verify_otp(VerifyOtpCommand("test@example.com", otp_code))


def test_verify_otp_expired() -> None:
    service, clock, otp_store, email_sender, _ = make_full_service()
    service.send_otp(SendOtpCommand("expire@example.com"))
    otp_code = email_sender.sent[0][1]

    # Advance 15 minutes (past 10 min TTL)
    clock.advance(15)
    with pytest.raises(AuthError):
        service.verify_otp(VerifyOtpCommand("expire@example.com", otp_code))


def test_register_with_otp() -> None:
    service, clock, otp_store, email_sender, _ = make_full_service()
    service.send_otp(SendOtpCommand("newuser@example.com"))
    otp_code = email_sender.sent[0][1]

    # Register with wrong OTP fails
    with pytest.raises(AuthError):
        service.register(
            None,
            RegisterCommand("New User", "newuser@example.com", "password123", otp="000000"),
        )

    # Register with correct OTP succeeds
    user = service.register(
        None,
        RegisterCommand("New User", "newuser@example.com", "password123", otp=otp_code),
    )
    assert user.email == "newuser@example.com"


def test_google_auth_flow() -> None:
    service, _, _, _, google_verifier = make_full_service()
    google_verifier.profiles["valid-token"] = GoogleProfile(
        email="googleuser@example.com",
        full_name="Google User",
        google_id="sub-12345",
    )

    # New user registers & logins via Google
    token, user = service.google_auth(None, GoogleAuthCommand(credential="valid-token"))
    assert token == f"token-{user.user_id}"
    assert user.email == "googleuser@example.com"
    assert user.full_name == "Google User"

    # Subsequent login returns the existing user
    token2, user2 = service.google_auth(None, GoogleAuthCommand(credential="valid-token"))
    assert user2.user_id == user.user_id
    assert token2 == token

    # Invalid credential raises AuthError
    with pytest.raises(AuthError):
        service.google_auth(None, GoogleAuthCommand(credential="bad-token"))
