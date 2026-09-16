from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisterCommand:
    full_name: str
    email: str
    password: str
    otp: str | None = None


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True)
class SendOtpCommand:
    email: str
    purpose: str = "verify_email"


@dataclass(frozen=True)
class VerifyOtpCommand:
    email: str
    otp: str
    purpose: str = "verify_email"


@dataclass(frozen=True)
class GoogleAuthCommand:
    credential: str
