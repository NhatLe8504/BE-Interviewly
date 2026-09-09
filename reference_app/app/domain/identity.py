from __future__ import annotations

from .errors import DomainValidationError

MIN_PASSWORD_LENGTH = 8


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    local, sep, domain = email.partition("@")
    if not sep or not local or "." not in domain:
        raise DomainValidationError("invalid email")
    return email


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise DomainValidationError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters",
        )


def validate_full_name(full_name: str) -> str:
    cleaned = full_name.strip()
    if not cleaned:
        raise DomainValidationError("full_name must not be blank")
    return cleaned
