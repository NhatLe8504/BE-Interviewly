from __future__ import annotations

import json
import re
import uuid
from typing import Any
import httpx


def build_question_generator_prompt(
    domain_name: str,
    role_name: str,
    experience_level: str,
    tech_stack: str,
    question_count: int,
    question_distribution: str,
    custom_prompt: str = "",
    source_type: str = "prompt",
    source_value: str = "",
) -> str:
    dist_desc = {
        "balanced": "Cân bằng giữa kỹ thuật (Technical), xử lý tình huống (Situational), và hành vi/văn hóa (Behavioral).",
        "technical_heavy": "70% Kỹ thuật chuyên sâu và kiến trúc hệ thống, 30% tình huống thực tế.",
        "behavioral_heavy": "70% Kỹ năng mềm, giải quyết xung đột, tinh thần đồng đội theo STAR, 30% kỹ thuật.",
        "situational": "Tập trung vào các tình huống thực tế khi vận hành, sự cố sản xuất (incident) và bài toán đánh đổi kỹ thuật.",
    }.get(question_distribution, "Cân bằng giữa các nhóm câu hỏi.")

    extra_context = ""
    if custom_prompt.strip():
        extra_context += f"\n- Yêu cầu trọng tâm từ chuyên gia: {custom_prompt.strip()}"
    if source_type in ("document", "url") and source_value.strip():
        extra_context += f"\n- Nội dung tài liệu/JD tham chiếu: {source_value.strip()[:1000]}"

    return f"""Bạn là Giám đốc phỏng vấn kỹ thuật và Tuyển dụng nhân sự cấp cao (Principal Technical Interviewer & HR Leader).
Nhiệm vụ của bạn là xây dựng ngân hàng gồm chính xác {question_count} câu hỏi phỏng vấn chuẩn hóa, thực tế, sâu sắc cho ứng viên sau:

- Lĩnh vực chuyên môn: {domain_name}
- Vị trí ứng tuyển (Role): {role_name}
- Cấp bậc kinh nghiệm: {experience_level}
- Công nghệ/Kỹ năng trọng tâm: {tech_stack or 'Không chỉ định (theo chuẩn ngành)'}
- Định hướng phân bổ: {dist_desc}
{extra_context}

YÊU CẦU ĐẦU RA BẮT BUỘC:
Trả về duy nhất một mảng JSON thuần túy (JSON Array), KHÔNG bọc trong markdown hay bất kỳ lời giải thích nào khác.
Mỗi phần tử trong mảng là một object có cấu trúc chính xác như sau:
[
  {{
    "id": "gen-1",
    "question_text": "Nội dung câu hỏi phỏng vấn rõ ràng, thực tế và có tính thử thách",
    "question_type": "technical", // một trong ba giá trị: "technical", "situational", "behavioral"
    "difficulty": 3, // số nguyên từ 1 (rất dễ) đến 5 (chuyên gia/lead)
    "intent": "Mục tiêu cụ thể nhà tuyển dụng muốn kiểm tra qua câu hỏi này",
    "situation_guide": "Gợi ý bối cảnh (S - Situation) ứng viên nên đưa ra theo mô hình STAR",
    "task_guide": "Gợi ý nhiệm vụ và trách nhiệm cốt lõi (T - Task) cần giải quyết",
    "action_guide": "Gợi ý các bước hành động chuyên môn cụ thể (A - Action) mang lại hiệu quả cao",
    "result_guide": "Gợi ý kết quả đo lường định lượng và bài học rút ra (R - Result)",
    "sample_answer": "Câu trả lời mẫu xuất sắc, súc tích và chuẩn mực (từ 2 đến 4 đoạn)",
    "follow_up_questions": [
      "Câu hỏi đào sâu thứ 1 nếu ứng viên trả lời tốt",
      "Câu hỏi đào sâu thứ 2 xoáy vào rủi ro/đánh đổi (trade-offs)"
    ],
    "tips": [
      "Mẹo ghi điểm cốt lõi 1 cho ứng viên",
      "Sai lầm thường gặp cần tránh 2"
    ],
    "tags": ["Kỹ năng 1", "Công nghệ 2", "Từ khóa 3"],
    "is_active": true,
    "status": "approved"
  }}
]
Hãy viết toàn bộ bằng tiếng Việt chuẩn mực ngành CNTT/Tuyển dụng chuyên nghiệp. Trả về đúng JSON.
"""


def generate_interview_questions_with_llm(
    *,
    domain_name: str = "Công nghệ thông tin (IT)",
    role_name: str = "Backend Engineer",
    experience_level: str = "junior",
    tech_stack: str = "Java, Spring Boot",
    question_count: int = 3,
    question_distribution: str = "balanced",
    custom_prompt: str = "",
    source_type: str = "prompt",
    source_value: str = "",
    base_url: str = "https://api.groq.com/openai/v1",
    api_key: str = "",
    model: str = "openai/gpt-oss-120b",
    timeout: float = 45.0,
) -> list[dict[str, Any]]:
    prompt = build_question_generator_prompt(
        domain_name=domain_name,
        role_name=role_name,
        experience_level=experience_level,
        tech_stack=tech_stack,
        question_count=question_count,
        question_distribution=question_distribution,
        custom_prompt=custom_prompt,
        source_type=source_type,
        source_value=source_value,
    )

    items: list[dict[str, Any]] = []

    if api_key:
        try:
            # Ưu tiên dùng model phù hợp trên Groq
            chosen_model = model
            if "gpt-oss-120b" in chosen_model:
                chosen_model = "openai/gpt-oss-120b"

            resp = httpx.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": chosen_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Bạn là chuyên gia thiết kế câu hỏi phỏng vấn chuẩn quốc tế. Luôn trả về định dạng JSON array hợp lệ.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 4096,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                payload = resp.json()
                content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
                items = extract_json_questions(content)
        except Exception:
            items = []

    if not items:
        # Fallback generator thông minh theo ngữ cảnh domain & role nếu LLM gặp trục trặc mạng
        items = generate_fallback_questions(
            domain_name=domain_name,
            role_name=role_name,
            experience_level=experience_level,
            tech_stack=tech_stack,
            question_count=question_count,
        )

    # Đảm bảo gán unique id cho từng câu hỏi
    for idx, item in enumerate(items, 1):
        if not item.get("id"):
            item["id"] = f"ai-q-{uuid.uuid4().hex[:8]}"
        item["status"] = "approved"
        item["is_active"] = True

    return items


def extract_json_questions(content: str) -> list[dict[str, Any]]:
    if not content:
        return []
    clean = content.strip()
    # Tìm mảng JSON [ ... ]
    m = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            pass

    # Tìm object { "questions": [...] }
    m_obj = re.search(r"\{\s*\"questions\"\s*:\s*(\[.*\])\s*\}", clean, re.DOTALL)
    if m_obj:
        try:
            parsed = json.loads(m_obj.group(1))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    return []


def generate_fallback_questions(
    domain_name: str,
    role_name: str,
    experience_level: str,
    tech_stack: str,
    question_count: int,
) -> list[dict[str, Any]]:
    level_num = {"intern": 1, "fresher": 2, "junior": 3, "mid": 3, "senior": 4, "lead": 5}.get(
        experience_level.lower(), 3
    )
    first_stack = tech_stack.split(",")[0].strip() if tech_stack else role_name

    templates = [
        {
            "id": f"fb-{uuid.uuid4().hex[:6]}",
            "question_text": f"Trong quá trình xây dựng ứng dụng với {first_stack}, bạn đã xử lý bài toán tối ưu hóa hiệu năng và quản lý tài nguyên bộ nhớ như thế nào?",
            "question_type": "technical",
            "difficulty": level_num,
            "intent": f"Đánh giá năng lực làm chủ kỹ thuật {first_stack}, tư duy cấu trúc mã nguồn và kiểm soát rò rỉ bộ nhớ/tắc nghẽn mạng.",
            "situation_guide": f"Mô tả một dự án hoặc module chịu tải lớn viết bằng {first_stack}.",
            "task_guide": "Xác định các chỉ số SLA cần đáp ứng (Response Time < 200ms, CPU < 70%).",
            "action_guide": f"Áp dụng profiling tools, tối ưu câu lệnh, caching và connection pooling trong {first_stack}.",
            "result_guide": "Tốc độ xử lý tăng gấp 2 lần, hạn chế triệt để lỗi out-of-memory.",
            "sample_answer": f"Khi phát triển hệ thống với {first_stack}, tôi luôn chú trọng việc tối ưu vòng đời đối tượng, sử dụng Connection Pool hợp lý và giám sát bằng APM metrics. Khi phát hiện điểm nghẽn, tôi phân tích thread dump và query plan để xử lý tận gốc.",
            "follow_up_questions": [
                f"Những công cụ profiling nào bạn thường dùng nhất cho {first_stack}?",
                "Bạn sẽ đánh đổi điều gì khi áp dụng cơ chế Caching nhiều tầng?",
            ],
            "tips": [
                "Nêu rõ các chỉ số đo lường trước và sau khi tối ưu.",
                "Trình bày logic xử lý từ tầng ứng dụng đến tầng cơ sở dữ liệu.",
            ],
            "tags": [first_stack, "Performance", "Optimization"],
            "is_active": True,
            "status": "approved",
        },
        {
            "id": f"fb-{uuid.uuid4().hex[:6]}",
            "question_text": f"Hãy kể về một lần xảy ra lỗi nghiêm trọng (Critical Bug) trên môi trường Production liên quan đến {role_name}. Bạn và đội ngũ đã khắc phục sự cố ra sao?",
            "question_type": "situational",
            "difficulty": max(2, level_num),
            "intent": "Khảo sát tư duy giải quyết sự cố dưới áp lực, kỹ năng làm việc nhóm và quy trình Post-Mortem.",
            "situation_guide": "Một đợt release vào cuối tuần gặp lỗi dẫn đến dữ liệu không đồng bộ.",
            "task_guide": "Phục hồi dịch vụ trong thời gian ngắn nhất (dưới 30 phút) và bảo vệ an toàn dữ liệu khách hàng.",
            "action_guide": "Kích hoạt Rollback tức thì, rà soát log ELK/Datadog, tái hiện lỗi trên Staging và viết hotfix kèm test cases bổ sung.",
            "result_guide": "Hệ thống phục hồi hoàn toàn sau 20 phút, tài liệu hóa nguyên nhân gốc rễ và bổ sung CI/CD integration tests.",
            "sample_answer": "Khi sự cố xảy ra, ưu tiên số một của tôi là cô lập rủi ro và khôi phục trạng thái ổn định cho người dùng bằng phương án Rollback hoặc Feature Flag. Sau đó, tôi phân tích root-cause qua log, viết hotfix và tổ chức buổi họp rút kinh nghiệm không đổ lỗi.",
            "follow_up_questions": [
                "Làm sao để hạn chế tối đa việc lặp lại sự cố tương tự trong tương lai?",
                "Nếu phương án Rollback cũng gặp lỗi do schema migration, bạn xử lý thế nào?",
            ],
            "tips": [
                "Giữ thái độ bình tĩnh, thể hiện tinh thần trách nhiệm cao.",
                "Nhấn mạnh vào quy trình phòng ngừa rủi ro dài hạn.",
            ],
            "tags": ["Incident Management", "Production", "Problem Solving"],
            "is_active": True,
            "status": "approved",
        },
        {
            "id": f"fb-{uuid.uuid4().hex[:6]}",
            "question_text": f"Khi bạn và Tech Lead hoặc đồng nghiệp bất đồng ý kiến sâu sắc về một giải pháp kỹ thuật trong dự án, bạn đã xử lý tình huống đó như thế nào?",
            "question_type": "behavioral",
            "difficulty": 3,
            "intent": "Đánh giá kỹ năng giao tiếp chuyên nghiệp, tinh thần hợp tác và sự linh hoạt khi tiếp nhận phản biện.",
            "situation_guide": "Hai giải pháp kiến trúc khác nhau cho cùng một bài toán Microservices vs Monolith.",
            "task_guide": "Thuyết phục đội ngũ hoặc tìm ra điểm chung tối ưu nhất mà không gây xung đột nội bộ.",
            "action_guide": "Xây dựng bảng ma trận so sánh ưu nhược điểm (Pros/Cons), làm Proof of Concept (PoC) nhỏ để kiểm chứng thực nghiệm bằng số liệu.",
            "result_guide": "Đội ngũ đồng thuận chọn giải pháp có số liệu chứng minh, dự án triển khai suôn sẻ và giữ được tinh thần đoàn kết cao.",
            "sample_answer": "Tôi tin rằng mọi tranh luận kỹ thuật đều nên dựa trên số liệu thực nghiệm thay vì cảm tính cá nhân. Tôi thường đề xuất làm một PoC nhanh hoặc lập bảng phân tích trade-off chi tiết để cả nhóm cùng đánh giá khách quan.",
            "follow_up_questions": [
                "Nếu quyết định cuối cùng đi ngược lại quan điểm của bạn, bạn sẽ làm gì?",
                "Bạn làm thế nào để duy trì tinh thần làm việc tích cực sau tranh luận căng thẳng?",
            ],
            "tips": [
                "Luôn dùng mô hình STAR để trả lời mạch lạc.",
                "Tập trung vào mục tiêu chung của sản phẩm và khách hàng.",
            ],
            "tags": ["Communication", "Conflict Resolution", "Teamwork"],
            "is_active": True,
            "status": "approved",
        },
    ]

    result = []
    for i in range(question_count):
        tmpl = templates[i % len(templates)].copy()
        tmpl["id"] = f"fb-{uuid.uuid4().hex[:6]}"
        result.append(tmpl)
    return result
