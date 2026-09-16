from __future__ import annotations

import pytest

from app.application.profile.commands import (
    ChangePasswordCommand,
    UpdateProfileCommand,
)
from app.application.profile.service import ProfileService
from app.domain.errors import AuthError, DomainValidationError, NotFoundError
from app.domain.profile import UserProfile


class FakeProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[int, UserProfile] = {}
        self.passwords: dict[int, str] = {}
        self.domains: set[int] = {1, 2}

    def get_profile_by_user_id(self, session, user_id: int) -> UserProfile | None:
        return self.profiles.get(user_id)

    def update_profile(
        self,
        session,
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
        current = self.profiles[user_id]
        if fields_set is None:
            updated = UserProfile(
                user_id=user_id,
                full_name=full_name if full_name is not None else current.full_name,
                email=current.email,
                phone=phone if phone is not None else current.phone,
                role=current.role,
                preferred_language=(
                    preferred_language
                    if preferred_language is not None
                    else current.preferred_language
                ),
                status=current.status,
                experience_level=(
                    experience_level
                    if experience_level is not None
                    else current.experience_level
                ),
                target_domain_id=(
                    target_domain_id
                    if target_domain_id is not None
                    else current.target_domain_id
                ),
                target_domain_name="Tech" if (target_domain_id or current.target_domain_id) else None,
                bio=bio if bio is not None else current.bio,
                avatar_url=avatar_url if avatar_url is not None else current.avatar_url,
            )
        else:
            updated = UserProfile(
                user_id=user_id,
                full_name=full_name if "full_name" in fields_set and full_name is not None else current.full_name,
                email=current.email,
                phone=phone if "phone" in fields_set else current.phone,
                role=current.role,
                preferred_language=(
                    preferred_language
                    if "preferred_language" in fields_set and preferred_language is not None
                    else current.preferred_language
                ),
                status=current.status,
                experience_level=(
                    experience_level
                    if "experience_level" in fields_set
                    else current.experience_level
                ),
                target_domain_id=(
                    target_domain_id
                    if "target_domain_id" in fields_set
                    else current.target_domain_id
                ),
                target_domain_name="Tech" if target_domain_id else None,
                bio=bio if "bio" in fields_set else current.bio,
                avatar_url=avatar_url if "avatar_url" in fields_set else current.avatar_url,
            )
        self.profiles[user_id] = updated
        return updated

    def get_password_hash(self, session, user_id: int) -> str | None:
        return self.passwords.get(user_id)

    def update_password(self, session, user_id: int, new_password_hash: str) -> None:
        self.passwords[user_id] = new_password_hash

    def domain_exists(self, session, domain_id: int) -> bool:
        return domain_id in self.domains


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed-{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed-{password}"


@pytest.fixture
def fake_env():
    repo = FakeProfileRepository()
    hasher = FakeHasher()
    service = ProfileService(repo=repo, hasher=hasher)
    user_id = 1
    repo.profiles[user_id] = UserProfile(
        user_id=user_id,
        full_name="Initial User",
        email="user@example.com",
        phone=None,
        role="candidate",
        preferred_language="vi",
        status="active",
    )
    repo.passwords[user_id] = "hashed-oldpassword123"
    return service, repo, user_id


def test_get_profile_success(fake_env) -> None:
    service, _, user_id = fake_env
    profile = service.get_profile(None, user_id)
    assert profile.user_id == user_id
    assert profile.full_name == "Initial User"
    assert profile.email == "user@example.com"


def test_get_profile_not_found(fake_env) -> None:
    service, _, _ = fake_env
    with pytest.raises(NotFoundError):
        service.get_profile(None, 999)


def test_update_profile_success(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = UpdateProfileCommand(
        full_name="Updated Name",
        phone="0912345678",
        preferred_language="en",
        experience_level="middle",
        target_domain_id=1,
        bio="Hello world",
        avatar_url="https://example.com/pic.png",
        fields_set=frozenset({
            "full_name",
            "phone",
            "preferred_language",
            "experience_level",
            "target_domain_id",
            "bio",
            "avatar_url",
        }),
    )
    res = service.update_profile(None, user_id, cmd)
    assert res.full_name == "Updated Name"
    assert res.phone == "0912345678"
    assert res.preferred_language == "en"
    assert res.experience_level == "middle"
    assert res.bio == "Hello world"
    assert res.avatar_url == "https://example.com/pic.png"


def test_update_profile_invalid_experience_level(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = UpdateProfileCommand(experience_level="god_tier")
    with pytest.raises(DomainValidationError, match="invalid experience level"):
        service.update_profile(None, user_id, cmd)


def test_update_profile_invalid_language(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = UpdateProfileCommand(preferred_language="fr")
    with pytest.raises(DomainValidationError, match="invalid preferred language"):
        service.update_profile(None, user_id, cmd)


def test_update_profile_target_domain_not_found(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = UpdateProfileCommand(target_domain_id=9999)
    with pytest.raises(NotFoundError, match="target domain 9999 not found"):
        service.update_profile(None, user_id, cmd)


def test_change_password_success(fake_env) -> None:
    service, repo, user_id = fake_env
    cmd = ChangePasswordCommand(
        current_password="oldpassword123",
        new_password="newpassword456",
    )
    service.change_password(None, user_id, cmd)
    assert repo.passwords[user_id] == "hashed-newpassword456"


def test_change_password_wrong_current(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = ChangePasswordCommand(
        current_password="wrongpassword",
        new_password="newpassword456",
    )
    with pytest.raises(AuthError, match="incorrect current password"):
        service.change_password(None, user_id, cmd)


def test_change_password_same_password_rejected(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = ChangePasswordCommand(
        current_password="oldpassword123",
        new_password="oldpassword123",
    )
    with pytest.raises(DomainValidationError, match="new password must be different"):
        service.change_password(None, user_id, cmd)


def test_change_password_short_password_rejected(fake_env) -> None:
    service, _, user_id = fake_env
    cmd = ChangePasswordCommand(
        current_password="oldpassword123",
        new_password="short",
    )
    with pytest.raises(DomainValidationError, match="at least 8 characters"):
        service.change_password(None, user_id, cmd)
