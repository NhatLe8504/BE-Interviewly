from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class JDTextSubmissionIn(BaseModel):
    text: str = Field(..., min_length=30, description="Nội dung Job Description")
    duration_minutes: int = Field(default=45, ge=15, le=90, description="Thời lượng phỏng vấn mục tiêu (phút)")
    difficulty: int | None = Field(default=None, ge=1, le=5, description="Độ khó mong muốn (1-5)")
    language: str = Field(default="vi", description="Ngôn ngữ phỏng vấn (vi hoặc en)")


class JDUrlSubmissionIn(BaseModel):
    url: str = Field(..., description="Đường link công khai của tin tuyển dụng")
    duration_minutes: int = Field(default=45, ge=15, le=90, description="Thời lượng phỏng vấn mục tiêu (phút)")
    difficulty: int | None = Field(default=None, ge=1, le=5, description="Độ khó mong muốn (1-5)")
    language: str = Field(default="vi", description="Ngôn ngữ phỏng vấn (vi hoặc en)")


class JDJobStatusOut(BaseModel):
    job_id: str
    status: str
    stage: str
    progress_pct: int
    result: dict[str, Any] | None = None
    error: str | None = None


class JDJobSummaryOut(BaseModel):
    job_id: str
    status: str
    stage: str
    progress_pct: int
    source_type: str
    role: str
    seniority: str
    company_name: str
    focus_areas: list[str] = Field(default_factory=list)
    total_questions: int = 0
    estimated_minutes: int = 45
    session_id: int | None = None
    created_at: str | None = None
    error: str | None = None


class JDStartSessionIn(BaseModel):
    mode: str = Field(default="text", description="text hoặc voice")
    barge_in_enabled: bool = Field(default=False)
    selected_stages: list[str] | None = None
    stage_configs: list[dict[str, Any]] | None = None