from __future__ import annotations

from typing import Any

from ...application.profile.ports import ProfileRepositoryPort
from ...domain.errors import NotFoundError
from ...domain.profile import UserProfile
from .models.catalog import JobDomain
from .models.enums import ExperienceLevel, Language
from .models.user import CandidateProfile, User


def _enum_value(val: Any) -> str | None:
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def _to_experience_level(val: str | None) -> ExperienceLevel | None:
    if val is None:
        return None
    if val == "middle":
        return ExperienceLevel.mid
    return ExperienceLevel(val)


class SqlAlchemyProfileRepository:
    def get_profile_by_user_id(self, session: Any, user_id: int) -> UserProfile | None:
        user = session.get(User, user_id)
        if user is None:
            return None

        profile = session.get(CandidateProfile, user_id)
        domain_name = None
        if profile is not None and profile.target_domain_id is not None:
            domain = session.get(JobDomain, profile.target_domain_id)
            if domain is not None:
                domain_name = domain.domain_name

        return UserProfile(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            phone=user.phone,
            role=_enum_value(user.role) or "candidate",
            preferred_language=_enum_value(user.preferred_language) or "vi",
            status=_enum_value(user.status) or "active",
            experience_level=_enum_value(profile.experience_level) if profile else None,
            target_domain_id=profile.target_domain_id if profile else None,
            target_domain_name=domain_name,
            bio=profile.bio if profile else None,
            avatar_url=profile.avatar_url if profile else None,
            created_at=user.created_at,
            updated_at=profile.updated_at if profile and profile.updated_at else user.updated_at,
        )

    def update_profile(
        self,
        session: Any,
        user_id: int,
        *,
        full_name: str | None = None,
        phone: str | None = None,
        preferred_language: str | None = None,
        experience_level: str | None = None,
        target_domain_id: int | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> UserProfile:
        user = session.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")

        profile = session.get(CandidateProfile, user_id)
        if profile is None:
            profile = CandidateProfile(user_id=user_id)
            session.add(profile)

        if fields_set is None:
            if full_name is not None:
                user.full_name = full_name
            if phone is not None:
                user.phone = phone
            if preferred_language is not None:
                user.preferred_language = Language(preferred_language)
            if experience_level is not None:
                profile.experience_level = _to_experience_level(experience_level)
            if target_domain_id is not None:
                profile.target_domain_id = target_domain_id
            if bio is not None:
                profile.bio = bio
            if avatar_url is not None:
                profile.avatar_url = avatar_url
        else:
            if "full_name" in fields_set and full_name is not None:
                user.full_name = full_name
            if "phone" in fields_set:
                user.phone = phone
            if "preferred_language" in fields_set and preferred_language is not None:
                user.preferred_language = Language(preferred_language)
            if "experience_level" in fields_set:
                profile.experience_level = _to_experience_level(experience_level)
            if "target_domain_id" in fields_set:
                profile.target_domain_id = target_domain_id
            if "bio" in fields_set:
                profile.bio = bio
            if "avatar_url" in fields_set:
                profile.avatar_url = avatar_url

        session.commit()
        session.refresh(user)
        session.refresh(profile)
        return self.get_profile_by_user_id(session, user_id)  # type: ignore[return-value]

    def get_password_hash(self, session: Any, user_id: int) -> str | None:
        user = session.get(User, user_id)
        return user.password_hash if user is not None else None

    def update_password(self, session: Any, user_id: int, new_password_hash: str) -> None:
        user = session.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        user.password_hash = new_password_hash
        session.commit()

    def domain_exists(self, session: Any, domain_id: int) -> bool:
        return session.get(JobDomain, domain_id) is not None
