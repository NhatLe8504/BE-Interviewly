from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ....application.profile.commands import (
    ChangePasswordCommand,
    UpdateProfileCommand,
)
from ....application.skills.service import UserSkillService
from ....application.skills.taxonomy import get_default_taxonomy
from ..dependencies import get_container, get_current_user_id, get_session
from ..schemas.profile import ChangePasswordIn, MessageOut, ProfileOut, ProfileUpdateIn
from ..schemas.user_skills import SkillEvidenceItemOut, SkillLevelItemOut, UserCareerProfileOut

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


@router.get("/skills", response_model=UserCareerProfileOut)
def get_my_skill_profile(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> UserCareerProfileOut:
    skill_svc = UserSkillService(session=session)
    career_rec = skill_svc.get_user_career_profile(user_id)
    skills_dict = skill_svc.get_user_skills_dict(user_id)
    taxonomy = get_default_taxonomy()

    skill_items = [
        SkillLevelItemOut(
            skill_id=s.skill_id,
            name=taxonomy.get_skill(s.skill_id).name if taxonomy.get_skill(s.skill_id) else s.skill_id,
            ability_score=s.ability_score,
            level=s.level,
            confidence=s.confidence,
            evidence_count=s.evidence_count,
            max_difficulty_passed=s.max_difficulty_passed,
        )
        for s in sorted(skills_dict.values(), key=lambda x: x.ability_score, reverse=True)
    ]

    return UserCareerProfileOut(
        user_id=user_id,
        primary_role_track=career_rec.primary_role_track if career_rec else None,
        secondary_role_track=career_rec.secondary_role_track if career_rec else None,
        role_confidence=float(career_rec.role_confidence) if career_rec else 0.0,
        overall_level=career_rec.overall_level if career_rec else "none",
        top_skills=career_rec.top_skills if career_rec else [],
        weak_skills=career_rec.weak_skills if career_rec else [],
        skills=skill_items,
    )


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
            mascot_id=data.mascot_id,
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


@router.get("/skills/{skill_id}/evidence", response_model=list[SkillEvidenceItemOut])
def get_my_skill_evidence(
    skill_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> list[SkillEvidenceItemOut]:
    skill_svc = UserSkillService(session=session)
    evs = skill_svc.get_skill_evidence(user_id, skill_id)
    return [
        SkillEvidenceItemOut(
            id=e.id,
            skill_id=e.skill_id,
            source_type=e.source_type,
            source_id=e.source_id,
            score=float(e.score),
            question_difficulty=e.question_difficulty,
            grader_confidence=float(e.grader_confidence),
            evidence_quote=e.evidence_quote,
            input_mode=e.input_mode,
            created_at=e.created_at,
        )
        for e in evs
    ]
