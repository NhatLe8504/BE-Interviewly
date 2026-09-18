from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain_id: int
    domain_name: str
    description: str | None = None
    created_at: datetime | None = None


class DomainCreateIn(BaseModel):
    domain_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class DomainUpdateIn(BaseModel):
    domain_name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    domain_id: int
    role_name: str
    description: str | None = None
    created_at: datetime | None = None


class RoleCreateIn(BaseModel):
    domain_id: int
    role_name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None


class RoleUpdateIn(BaseModel):
    role_name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    domain_id: int | None = None


class StarTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    star_template_id: int
    title: str
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = "vi"
    created_at: datetime | None = None


class StarTemplateCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = Field("vi", pattern="^(vi|en)$")


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    domain_id: int
    role_id: int | None = None
    experience_level: str | None = None
    language: str = "vi"
    question_type: str
    question_text: str
    star_template_id: int | None = None
    is_active: bool = True
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QuestionDetailOut(QuestionOut):
    star_template: StarTemplateOut | None = None


class QuestionCreateIn(BaseModel):
    domain_id: int
    question_text: str = Field(..., min_length=1)
    question_type: str = Field(..., pattern="^(behavioral|technical|situational)$")
    language: str = Field("vi", pattern="^(vi|en)$")
    role_id: int | None = None
    experience_level: str | None = Field(
        None, pattern="^(intern|fresher|junior|mid|middle|senior)$",
    )
    star_template_id: int | None = None


class QuestionUpdateIn(BaseModel):
    question_text: str | None = Field(None, min_length=1)
    question_type: str | None = Field(
        None, pattern="^(behavioral|technical|situational)$",
    )
    language: str | None = Field(None, pattern="^(vi|en)$")
    role_id: int | None = None
    experience_level: str | None = Field(
        None, pattern="^(intern|fresher|junior|mid|middle|senior)$",
    )
    star_template_id: int | None = None
    is_active: bool | None = None


class QuestionPageOut(BaseModel):
    items: list[QuestionOut]
    total: int
    limit: int
    offset: int
