from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SkillLevelItemOut(BaseModel):
    skill_id: str
    name: str
    ability_score: float
    level: str
    confidence: float
    evidence_count: int
    max_difficulty_passed: int


class UserCareerProfileOut(BaseModel):
    user_id: int
    primary_role_track: str
    secondary_role_track: str | None = None
    role_confidence: float = 0.0
    overall_level: str = "none"
    top_skills: list[dict[str, Any]] = Field(default_factory=list)
    weak_skills: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[SkillLevelItemOut] = Field(default_factory=list)


class JobReadinessRequirementOut(BaseModel):
    skill_id: str
    name: str
    importance: str
    required_level: str
    user_level: str
    status: str
    confidence: float = 0.0
    level_assumed: bool = False


class JobReadinessAssessmentOut(BaseModel):
    job_id: str
    match_percent: int
    verdict: str
    data_coverage: float
    requirements: list[JobReadinessRequirementOut]
    explanation: str
    recommended_skills: list[str] = Field(default_factory=list)
