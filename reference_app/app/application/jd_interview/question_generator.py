from __future__ import annotations

import asyncio
import difflib
import logging
import re
from typing import Any
import uuid
import httpx

from ...domain.errors import DomainValidationError
from ...domain.jd_interview import (
    BlueprintSection,
    InterviewBlueprint,
    InterviewScript,
    JobAnalysis,
    ScriptItem,
    JDSectionType,
)
from .analyzer_service import _extract_json_from_llm
from .prompts import build_competency_question_prompt
from .schemas import CompetencyBatchOutputSchema

logger = logging.getLogger(__name__)


class ParallelQuestionGenerator:
    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model or "llama-3.3-70b-versatile"
        if api_key.startswith("gsk_"):
            self.base_url = "https://api.groq.com/openai/v1"
        else:
            self.base_url = base_url.rstrip("/")

    async def _generate_section_questions(
        self,
        section: BlueprintSection,
        role: str,
        seniority: str,
        required_skills: list[str],
        language: str,
    ) -> list[ScriptItem]:
        competency = section.target_competencies[0] if section.target_competencies else role
        prompt = build_competency_question_prompt(
            role=role,
            seniority=seniority,
            competency=competency,
            section_type=section.section_type,
            question_count=section.question_count,
            difficulty=3,
            required_skills=required_skills,
            language=language,
        )

        items: list[ScriptItem] = []
        if self.api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a professional technical interviewer who only outputs valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.4,
                    "max_tokens": 2048,
                }
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = _extract_json_from_llm(content)

                    if parsed and "questions" in parsed:
                        batch = CompetencyBatchOutputSchema(**parsed)
                        for idx, q in enumerate(batch.questions):
                            items.append(
                                ScriptItem(
                                    order_index=idx + 1,
                                    section_type=section.section_type,
                                    competency_name=competency,
                                    question_text=q.question_text,
                                    rationale=q.rationale,
                                    difficulty=q.difficulty,
                                    expected_signals=q.expected_signals or ["Ứng viên trình bày có cấu trúc rõ ràng."],
                                    red_flags=q.red_flags or ["Ứng viên lúng túng hoặc trả lời sai trọng tâm."],
                                    sample_good_answer=q.sample_good_answer,
                                    follow_up_probes=q.follow_up_probes,
                                )
                            )
            except Exception as exc:
                logger.warning("Parallel LLM question gen failed for %s: %s", competency, exc)

        # Fallback if LLM generated fewer questions than requested
        needed = section.question_count - len(items)
        if needed > 0:
            fallback_items = self._build_curated_fallback_questions(
                section=section,
                role=role,
                seniority=seniority,
                required_skills=required_skills,
                count=needed,
                start_index=len(items) + 1,
            )
            items.extend(fallback_items)

        return items

    def _build_curated_fallback_questions(
        self,
        section: BlueprintSection,
        role: str,
        seniority: str,
        required_skills: list[str],
        count: int,
        start_index: int,
    ) -> list[ScriptItem]:
        competency = section.target_competencies[0] if section.target_competencies else role
        primary_skill = required_skills[0] if required_skills else "công nghệ chính"
        secondary_skill = required_skills[1] if len(required_skills) > 1 else "cơ sở dữ liệu"

        templates: dict[str, list[dict[str, Any]]] = {
            JDSectionType.introduction.value: [
                {
                    "q": f"Chào bạn! Bạn hãy giới thiệu ngắn gọn về hành trình làm việc và những dự án trọng điểm giúp bạn tự tin ứng tuyển vị trí {role} ({seniority})?",
                    "r": "Kiểm tra kỹ năng tổng hợp thông tin, định vị thế mạnh bản thân và phong thái giao tiếp ban đầu.",
                    "diff": 2,
                    "signals": ["Trình bày ngắn gọn trong 2 phút", "Nêu bật các dự án liên quan trực tiếp đến JD", "Định hướng rõ ràng"],
                    "red_flags": ["Kể lể lan man không trọng tâm", "Không nhớ rõ vai trò của mình trong dự án"],
                    "probes": ["Điểm gì trong dự án đó mà bạn cảm thấy thử thách nhất?", "Nếu được làm lại, bạn sẽ thay đổi điều gì?"],
                }
            ],
            JDSectionType.technical.value: [
                {
                    "q": f"Trong các dự án gần đây sử dụng {primary_skill}, bạn đã tổ chức cấu trúc mã nguồn và quản lý luồng dữ liệu như thế nào để đảm bảo tính module hóa và dễ mở rộng?",
                    "r": f"Đánh giá năng lực sử dụng {primary_skill} ở cấp độ thực chiến và tuân thủ các nguyên tắc thiết kế phần mềm sạch.",
                    "diff": 3,
                    "signals": ["Hiểu rõ Clean Architecture / Design Patterns", "Biết cách xử lý dependency injection và decoupling", "Chú trọng unit test"],
                    "red_flags": ["Viết code dồn tất cả vào một file", "Không phân biệt được business logic và data access"],
                    "probes": [f"Bạn xử lý error handling và logging trong {primary_skill} thế nào?", "Làm sao để đảm bảo code testable?"],
                },
                {
                    "q": f"Khi làm việc với {secondary_skill} trong môi trường tải cao, bạn áp dụng những kỹ thuật nào để tối ưu truy vấn, tránh race condition và kiểm soát connection pool?",
                    "r": f"Kiểm tra hiểu biết sâu về vận hành {secondary_skill}, index optimization và tính toàn vẹn dữ liệu.",
                    "diff": 4,
                    "signals": ["Biết phân tích execution plan", "Hiểu các cấp độ transaction isolation", "Biết cấu hình pool size phù hợp"],
                    "red_flags": ["N+1 queries không được xử lý", "Lạm dụng full table scan hoặc thiếu index quan trọng"],
                    "probes": ["Làm sao bạn phát hiện ra slow query trên production?", "Bạn xử lý dead lock như thế nào?"],
                },
                {
                    "q": f"Bạn hãy giải thích chiến lược caching đa tầng (in-memory, distributed cache như Redis) và cách bạn xử lý bài toán Cache Stampede (Cache Avalanche)?",
                    "r": "Đánh giá kiến thức phân tán và tối ưu hiệu năng hệ thống chịu tải lớn.",
                    "diff": 4,
                    "signals": ["Phân biệt Cache-aside, Write-through", "Biết áp dụng Mutex/Lock hoặc Probabilistic early expiration", "Hiểu TTL jitter"],
                    "red_flags": ["Không biết rủi ro khi cache expire đồng loạt", "Lưu dữ liệu nhạy cảm vào cache không mã hóa"],
                    "probes": ["Khi DB cập nhật thì làm sao invalidate cache chính xác?", "Xử lý thế nào nếu Redis cluster tạm thời ngắt kết nối?"],
                },
            ],
            JDSectionType.scenario.value: [
                {
                    "q": f"Giả sử hệ thống của bạn đột ngột tăng lưu lượng gấp 10 lần trong 1 giờ cao điểm, các worker xử lý nền bị nghẽn và latency API tăng vọt. Bạn sẽ thực hiện các bước chẩn đoán và khắc phục khẩn cấp như thế nào?",
                    "r": "Kiểm tra kỹ năng incident management, tư duy phân tích log/metrics và năng lực xử lý sự cố thực tế.",
                    "diff": 4,
                    "signals": ["Bình tĩnh phân loại nút thắt cổ chai (CPU, Memory, DB connection, Network)", "Áp dụng rate limiting, circuit breaker hoặc graceful degradation", "Ghi nhận post-mortem"],
                    "red_flags": ["Hoảng loạn restart bừa bãi không phân tích log", "Không có cơ chế bảo vệ DB chống sập dây chuyền"],
                    "probes": ["Nếu database CPU đạt 100%, hành động đầu tiên của bạn là gì?", "Làm thế nào để thông báo cho khách hàng mà không làm xấu uy tín?"],
                },
                {
                    "q": f"Khi cần chuyển đổi (refactor) một service nguyên khối (monolith) cũ sang kiến trúc hướng dịch vụ hoặc module hóa mà không làm gián đoạn người dùng hiện tại, bạn sẽ áp dụng chiến lược nào?",
                    "r": "Đánh giá khả năng chuyển đổi hệ thống legacy và áp dụng các mẫu kiến trúc như Strangler Fig.",
                    "diff": 4,
                    "signals": ["Áp dụng Strangler Fig pattern", "Dual-write và verification song song", "Rollback plan chi tiết"],
                    "red_flags": ["Đập đi xây lại từ đầu mà không có kế hoạch chuyển giao", "Không có chiến lược sync dữ liệu 2 chiều"],
                    "probes": ["Làm sao đảm bảo tính nhất quán dữ liệu giữa 2 hệ thống?", "Khi nào thì được phép tắt hoàn toàn code cũ?"],
                },
            ],
            JDSectionType.behavioral.value: [
                {
                    "q": "Hãy kể lại một lần bạn có bất đồng quan điểm kỹ thuật sâu sắc với Tech Lead hoặc đồng nghiệp về một giải pháp kiến trúc. Bạn đã giải quyết mâu thuẫn đó như thế nào và kết quả ra sao?",
                    "r": "Đánh giá kỹ năng giao tiếp, thái độ lắng nghe, khả năng dùng dữ liệu để thuyết phục và tinh thần vì mục tiêu chung.",
                    "diff": 3,
                    "signals": ["Dùng benchmark và số liệu thực tế thay vì cảm tính", "Tôn trọng quyết định chung sau khi đã thảo luận (Disagree and Commit)", "Mối quan hệ đồng nghiệp vẫn tốt đẹp"],
                    "red_flags": ["Bảo thủ cố chấp", "Bằng mặt không bằng lòng, trì hoãn công việc"],
                    "probes": ["Nếu kết quả cuối cùng chứng minh bạn đúng, bạn sẽ ứng xử thế nào?", "Bạn rút ra bài học gì cho những lần sau?"],
                },
                {
                    "q": "Chia sẻ về một lần dự án bị trễ hạn chót (deadline) do yêu cầu thay đổi liên tục từ phía khách hàng/Product Owner. Bạn đã ưu tiên công việc và trao đổi lại như thế nào?",
                    "r": "Đánh giá năng lực quản lý kỳ vọng, khả năng cắt tỉa phạm vi tính năng (scope pruning) và chịu áp lực.",
                    "diff": 3,
                    "signals": ["Chủ động cảnh báo sớm về rủi ro trễ hạn", "Đề xuất giải pháp MVP khả thi để release đúng hẹn", "Giữ vững chất lượng code tối thiểu"],
                    "red_flags": ["Im lặng làm overtime đến khi sát ngày mới báo vỡ kế hoạch", "Đổ lỗi hoàn toàn cho Product Owner"],
                    "probes": ["Bạn nói 'Không' với một yêu cầu bổ sung như thế nào?", "Làm sao bảo vệ nhóm khỏi tình trạng burnout?"],
                },
            ],
            JDSectionType.closing.value: [
                {
                    "q": f"Trước khi kết thúc, bạn có câu hỏi nào muốn dành cho chúng tôi về văn hóa làm việc, lộ trình phát triển của vị trí {role}, hay định hướng công nghệ của công ty không?",
                    "r": "Đánh giá sự chuẩn bị, mức độ quan tâm nghiêm túc của ứng viên đối với vai trò và môi trường doanh nghiệp.",
                    "diff": 1,
                    "signals": ["Đặt câu hỏi có chiều sâu về văn hóa, team hoặc roadmap công nghệ", "Thể hiện tinh thần học hỏi và đóng góp lâu dài"],
                    "red_flags": ["Không có bất kỳ câu hỏi nào", "Chỉ chăm chăm hỏi về quyền lợi mà không quan tâm công việc"],
                    "probes": ["Điều gì quan trọng nhất với bạn khi chọn một môi trường làm việc mới?"],
                }
            ],
        }

        section_templates = templates.get(section.section_type, templates[JDSectionType.technical.value])
        generated: list[ScriptItem] = []

        for i in range(count):
            tpl = section_templates[i % len(section_templates)]
            generated.append(
                ScriptItem(
                    order_index=start_index + i,
                    section_type=section.section_type,
                    competency_name=competency,
                    question_text=tpl["q"],
                    rationale=tpl["r"],
                    difficulty=tpl["diff"],
                    expected_signals=tpl["signals"],
                    red_flags=tpl["red_flags"],
                    sample_good_answer=f"Ứng viên áp dụng mô hình STAR: Nêu bối cảnh (Situation), nhiệm vụ (Task), các hành động kỹ thuật cụ thể (Action), và kết quả định lượng đạt được (Result).",
                    follow_up_probes=tpl["probes"],
                )
            )

        return generated

    async def generate_all_questions_parallel(
        self,
        blueprint: InterviewBlueprint,
        analysis: JobAnalysis,
        language: str = "vi",
    ) -> list[ScriptItem]:
        tasks = [
            self._generate_section_questions(
                section=section,
                role=blueprint.target_role,
                seniority=blueprint.seniority,
                required_skills=analysis.required_skills,
                language=language,
            )
            for section in blueprint.sections
        ]

        # Parallel execution across all sections
        section_results = await asyncio.gather(*tasks)

        all_items: list[ScriptItem] = []
        for batch in section_results:
            all_items.extend(batch)

        return all_items


class QuestionAggregator:
    @staticmethod
    def _is_semantically_duplicate(q1: str, q2: str, threshold: float = 0.72) -> bool:
        # Normalize simple punctuation and casing
        norm1 = re.sub(r"[^\w\s]", "", q1.lower()).strip()
        norm2 = re.sub(r"[^\w\s]", "", q2.lower()).strip()
        ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        return ratio >= threshold

    @classmethod
    def aggregate_and_deduplicate(
        cls,
        raw_items: list[ScriptItem],
        blueprint: InterviewBlueprint,
    ) -> InterviewScript:
        unique_items: list[ScriptItem] = []

        # Deduplication pass
        for item in raw_items:
            is_dup = False
            for existing in unique_items:
                if cls._is_semantically_duplicate(item.question_text, existing.question_text):
                    is_dup = True
                    break
            if not is_dup:
                unique_items.append(item)

        # Ordering pass: Ensure logical progression
        section_order_priority = {
            JDSectionType.introduction.value: 1,
            JDSectionType.technical.value: 2,
            JDSectionType.scenario.value: 3,
            JDSectionType.system_design.value: 4,
            JDSectionType.role_specific.value: 5,
            JDSectionType.behavioral.value: 6,
            JDSectionType.closing.value: 7,
        }

        sorted_items = sorted(
            unique_items,
            key=lambda x: (section_order_priority.get(x.section_type, 99), -x.difficulty),
        )

        final_items: list[ScriptItem] = []
        for index, item in enumerate(sorted_items, start=1):
            final_items.append(
                ScriptItem(
                    order_index=index,
                    section_type=item.section_type,
                    competency_name=item.competency_name,
                    question_text=item.question_text,
                    rationale=item.rationale,
                    difficulty=item.difficulty,
                    expected_signals=item.expected_signals,
                    red_flags=item.red_flags,
                    sample_good_answer=item.sample_good_answer,
                    follow_up_probes=item.follow_up_probes,
                )
            )

        script_id = f"script_{uuid.uuid4().hex[:12]}"
        return InterviewScript(
            script_id=script_id,
            total_questions=len(final_items),
            estimated_minutes=blueprint.total_duration_minutes,
            items=final_items,
        )


class QualityGateValidator:
    @staticmethod
    def validate_script(
        script: InterviewScript,
        analysis: JobAnalysis,
    ) -> tuple[bool, list[str]]:
        warnings: list[str] = []

        if script.total_questions < 4:
            warnings.append("Tổng số câu hỏi ít hơn khuyến nghị (tối thiểu 4 câu).")

        # Check required skill coverage in question texts or rationales
        combined_text = " ".join(
            (item.question_text + " " + item.rationale + " " + " ".join(item.expected_signals)).lower()
            for item in script.items
        )

        matched_skills = [
            skill for skill in analysis.required_skills
            if re.search(r"\b" + re.escape(skill.lower()) + r"\b", combined_text)
        ]

        if analysis.required_skills:
            coverage_pct = len(matched_skills) / len(analysis.required_skills)
            if coverage_pct < 0.3:
                warnings.append(f"Độ phủ kỹ năng bắt buộc đạt {int(coverage_pct * 100)}%. Có thể bổ sung thêm câu hỏi chuyên sâu.")

        passed = len(warnings) == 0 or script.total_questions >= 3
        return passed, warnings
