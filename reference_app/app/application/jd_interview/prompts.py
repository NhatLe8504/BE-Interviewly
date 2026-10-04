from __future__ import annotations

PROMPT_VERSIONS = {
    "jd_analysis": "v1.0.0",
    "blueprint_planning": "v1.0.0",
    "question_generation": "v1.0.0",
    "quality_validation": "v1.0.0",
}


def build_jd_analysis_system_prompt() -> str:
    return """Bạn là chuyên gia phân tích yêu cầu tuyển dụng (Technical Talent Assessment Specialist).
Nhiệm vụ của bạn là phân tích văn bản Job Description (JD) được cung cấp và trích xuất cấu trúc năng lực chuẩn xác dưới dạng JSON.

QUY TẮC BẮT BUỘC:
1. Trả về DUY NHẤT một chuỗi JSON hợp lệ theo đúng cấu trúc schema yêu cầu.
2. Không thêm markdown code block, không thêm giải thích hay chữ bên ngoài JSON.
3. Không tự bịa đặt thông tin không có trong JD; nếu không có, để danh sách rỗng [] hoặc null.
4. Cấp độ seniority PHẢI là một trong các giá trị: intern, fresher, junior, mid, senior, lead, staff, principal.
5. Ngôn ngữ output giữ nguyên theo ngôn ngữ của JD (tiếng Việt hoặc tiếng Anh)."""


def build_jd_analysis_user_prompt(cleaned_jd_text: str, language: str) -> str:
    return f"""Dưới đây là nội dung Job Description cần phân tích (ngôn ngữ chính: {language}):

=== BẮT ĐẦU JD ===
{cleaned_jd_text}
=== KẾT THÚC JD ===

Hãy trả về JSON với các trường:
{{
  "job_title": "string",
  "company_name": "string hoặc null",
  "seniority": "intern | fresher | junior | mid | senior | lead | staff | principal",
  "employment_type": "string hoặc null",
  "location": "string hoặc null",
  "responsibilities": ["string"],
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "technologies": ["string"],
  "domain_knowledge": ["string"],
  "soft_skills": ["string"],
  "technical_signals": ["string"],
  "behavioral_signals": ["string"],
  "confidence_score": 0.95
}}"""


def build_competency_question_prompt(
    role: str,
    seniority: str,
    competency: str,
    section_type: str,
    question_count: int,
    difficulty: int,
    required_skills: list[str],
    language: str,
) -> str:
    lang_instruction = "Viết bằng tiếng Việt tự nhiên, chuẩn ngữ cảnh phỏng vấn kỹ thuật." if language == "vi" else "Write in fluent, professional English suited for technical interviews."
    skills_context = ", ".join(required_skills[:10]) if required_skills else role

    return f"""Bạn là Lead Interviewer đang thiết kế câu hỏi phỏng vấn cho vị trí {role} ({seniority}).
Nhóm năng lực cần đánh giá: "{competency}" (Phần thi: {section_type}).
Kỹ năng liên quan từ JD: {skills_context}.
Độ khó mục tiêu: {difficulty}/5.
Số lượng câu hỏi cần sinh: {question_count} câu hỏi.
{lang_instruction}

QUY TẮC:
1. Câu hỏi phải thực tế, đào sâu bản chất vấn đề, tình huống thực tế mà kỹ sư thường gặp, không hỏi lý thuyết sáo rỗng.
2. Trả về DUY NHẤT một JSON hợp lệ:
{{
  "competency_name": "{competency}",
  "questions": [
    {{
      "competency_name": "{competency}",
      "question_text": "Nội dung câu hỏi phỏng vấn rõ ràng, súc tích",
      "rationale": "Mục đích đánh giá câu hỏi này dựa trên JD",
      "difficulty": {difficulty},
      "expected_signals": ["Tín hiệu ứng viên hiểu sâu...", "Tín hiệu đưa ra giải pháp tối ưu..."],
      "red_flags": ["Dấu hiệu nhận biết ứng viên hời hợt hoặc sai kiến thức cơ bản..."],
      "sample_good_answer": "Gợi ý câu trả lời mẫu chuẩn phương pháp STAR",
      "follow_up_probes": ["Câu hỏi phụ 1...", "Câu hỏi phụ 2..."]
    }}
  ]
}}"""
