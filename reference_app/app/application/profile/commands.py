from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UpdateProfileCommand:
    full_name: str | None = None
    phone: str | None = None
    preferred_language: str | None = None
    experience_level: str | None = None
    target_domain_id: int | None = None
    bio: str | None = None
    avatar_url: str | None = None
    fields_set: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ChangePasswordCommand:
    current_password: str
    new_password: str
