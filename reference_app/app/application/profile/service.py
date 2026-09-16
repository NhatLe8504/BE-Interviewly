from __future__ import annotations

from typing import Any

from ...domain.errors import AuthError, DomainValidationError, NotFoundError
from ...domain.identity import validate_full_name, validate_password
from ...domain.profile import (
    UserProfile,
    validate_avatar_url,
    validate_bio,
    validate_experience_level,
    validate_language,
    validate_phone,
)
from .commands import ChangePasswordCommand, UpdateProfileCommand
from .ports import PasswordHasherPort, ProfileRepositoryPort


class ProfileService:
    def __init__(
        self,
        repo: ProfileRepositoryPort,
        hasher: PasswordHasherPort,
    ) -> None:
        self.repo = repo
        self.hasher = hasher

    def get_profile(self, session: Any, user_id: int) -> UserProfile:
        profile = self.repo.get_profile_by_user_id(session, user_id)
        if profile is None:
            raise NotFoundError("user not found")
        return profile

    def update_profile(
        self,
        session: Any,
        user_id: int,
        cmd: UpdateProfileCommand,
    ) -> UserProfile:
        existing = self.repo.get_profile_by_user_id(session, user_id)
        if existing is None:
            raise NotFoundError("user not found")

        if cmd.full_name is not None:
            validate_full_name(cmd.full_name)
        if cmd.preferred_language is not None:
            validate_language(cmd.preferred_language)
        if cmd.experience_level is not None:
            validate_experience_level(cmd.experience_level)
        if cmd.phone is not None:
            validate_phone(cmd.phone)
        if cmd.bio is not None:
            validate_bio(cmd.bio)
        if cmd.avatar_url is not None:
            validate_avatar_url(cmd.avatar_url)
        if cmd.target_domain_id is not None:
            if not self.repo.domain_exists(session, cmd.target_domain_id):
                raise NotFoundError(f"target domain {cmd.target_domain_id} not found")

        return self.repo.update_profile(
            session,
            user_id,
            full_name=cmd.full_name,
            phone=cmd.phone,
            preferred_language=cmd.preferred_language,
            experience_level=cmd.experience_level,
            target_domain_id=cmd.target_domain_id,
            bio=cmd.bio,
            avatar_url=cmd.avatar_url,
            fields_set=cmd.fields_set if cmd.fields_set else None,
        )

    def change_password(
        self,
        session: Any,
        user_id: int,
        cmd: ChangePasswordCommand,
    ) -> None:
        validate_password(cmd.new_password)
        if cmd.current_password == cmd.new_password:
            raise DomainValidationError("new password must be different from current password")

        stored_hash = self.repo.get_password_hash(session, user_id)
        if stored_hash is None:
            raise NotFoundError("user not found")

        if not self.hasher.verify(cmd.current_password, stored_hash):
            raise AuthError("incorrect current password")

        new_hash = self.hasher.hash(cmd.new_password)
        self.repo.update_password(session, user_id, new_hash)
