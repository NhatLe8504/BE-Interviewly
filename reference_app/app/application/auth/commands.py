from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisterCommand:
    full_name: str
    email: str
    password: str


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
