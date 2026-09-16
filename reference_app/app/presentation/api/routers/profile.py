from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ....application.container import ServiceContainer
from ....application.profile.commands import (
    ChangePasswordCommand,
    UpdateProfileCommand,
)
from ..dependencies import get_container, get_current_user_id, get_session
from ..schemas.profile import ChangePasswordIn, MessageOut, ProfileOut, ProfileUpdateIn

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
@router.get("/me", response_model=ProfileOut)
def get_my_profile(
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ProfileOut:
    profile = container.profile_service.get_profile(session, user_id)
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
@router.patch("", response_model=ProfileOut)
def update_my_profile(
    data: ProfileUpdateIn,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ProfileOut:
    profile = container.profile_service.update_profile(
        session,
        user_id,
        UpdateProfileCommand(
            full_name=data.full_name,
            phone=data.phone,
            preferred_language=data.preferred_language,
            experience_level=data.experience_level,
            target_domain_id=data.target_domain_id,
            bio=data.bio,
            avatar_url=data.avatar_url,
            fields_set=frozenset(data.model_fields_set),
        ),
    )
    return ProfileOut.model_validate(profile)


@router.post("/change-password", response_model=MessageOut)
def change_my_password(
    data: ChangePasswordIn,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> MessageOut:
    container.profile_service.change_password(
        session,
        user_id,
        ChangePasswordCommand(
            current_password=data.current_password,
            new_password=data.new_password,
        ),
    )
    return MessageOut(message="Password changed successfully")
