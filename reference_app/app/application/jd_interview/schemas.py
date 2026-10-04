from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class JobAnalysisExtractionSchema(BaseModel):
    job_title: str = Field(..., description="Tên chức danh công việc chính xác")
    company_name: str | None = Field(default=None, description="Tên công ty tuyển dụng nếu có")
    seniority: str = Field(
        default="junior",
        description="Cấp độ kinh nghiệm: intern, fresher, junior, mid, senior, lead, staff, principal",
    )
    employment_type: str | None = Field(default=None, description="Toàn thời gian, bán thời gian, remote...")
    location: str | None = Field(default=None, description="Địa điểm làm việc")
    responsibilities: list[str] = Field(default_factory=list, description="Danh sách trách nhiệm chính")
    required_skills: list[str] = Field(default_factory=list, description="Kỹ năng bắt buộc")
    preferred_skills: list[str] = Field(default_factory=list, description="Kỹ năng ưu tiên / điểm cộng")
    technologies: list[str] = Field(default_factory=list, description="Công nghệ, ngôn ngữ, công cụ, framework")
    domain_knowledge: list[str] = Field(default_factory=list, description="Kiến thức ngành, nghiệp vụ")
    soft_skills: list[str] = Field(default_factory=list, description="Kỹ năng mềm, giao tiếp, làm việc nhóm")
    technical_signals: list[str] = Field(default_factory=list, description="Dấu hiệu cho thấy ứng viên thành thạo kỹ thuật")
    behavioral_signals: list[str] = Field(default_factory=list, description="Dấu hiệu về thái độ và văn hóa phù hợp")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Độ tin cậy của việc trích xuất")

    @field_validator("seniority")
    @classmethod
    def validate_seniority(cls, val: str) -> str:
        cleaned = val.strip().lower()
        valid = {"intern", "fresher", "junior", "mid", "senior", "lead", "staff", "principal"}
        if cleaned in valid:
            return cleaned
        if "lead" in cleaned or "trưởng" in cleaned:
            return "lead"
        if "senior" in cleaned or "chính" in cleaned:
            return "senior"
        if "mid" in cleaned:
            return "mid"
        if "fresher" in cleaned:
            return "fresher"
        if "intern" in cleaned or "thực tập" in cleaned:
            return "intern"
        return "junior"


class CompetencyQuestionSchema(BaseModel):
    competency_name: str = Field(..., description="Tên năng lực đánh giá")
    question_text: str = Field(..., description="Nội dung câu hỏi phỏng vấn")
    rationale: str = Field(..., description="Mục đích và lý do hỏi câu này từ JD")
    difficulty: int = Field(default=3, ge=1, le=5, description="Độ khó từ 1 đến 5")
    expected_signals: list[str] = Field(default_factory=list, description="Những tín hiệu mong đợi trong câu trả lời")
    red_flags: list[str] = Field(default_factory=list, description="Những cảnh báo hoặc lỗi sai nghiêm trọng")
    sample_good_answer: str | None = Field(default=None, description="Câu trả lời mẫu ngắn gọn chuẩn STAR")
    follow_up_probes: list[str] = Field(default_factory=list, description="2-3 câu hỏi phụ đào sâu tình huống")


class CompetencyBatchOutputSchema(BaseModel):
    competency_name: str
    questions: list[CompetencyQuestionSchema] = Field(default_factory=list)
