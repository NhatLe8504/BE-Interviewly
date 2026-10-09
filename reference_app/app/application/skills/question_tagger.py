from __future__ import annotations

from dataclasses import dataclass, field

from .taxonomy import SkillTaxonomy, get_default_taxonomy

# Câu hỏi hành vi/tình huống đo kỹ năng mềm theo thiết kế, nên những nhãn kỹ năng
# mềm dưới đây được GIỮ dù không xuất hiện nguyên văn trong câu hỏi.
# Mọi nhãn công nghệ (định dạng/framework/database...) vẫn phải có bằng chứng văn bản
# trong chính câu hỏi — không suy đoán theo domain hay sample_answer (LOI #7).
SOFT_SKILL_IDS = frozenset({"communication", "problem-solving"})
SOFT_QUESTION_TYPES = frozenset({"behavioral", "situational"})


@dataclass
class QuestionTagAudit:
    question_id: int
    question_type: str
    current: list[str]
    final: list[str]
    evidence: list[str]
    added: list[str]
    dropped: list[str]
    unknown_dropped: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.dropped or self.unknown_dropped)


def _normalize_type(question_type) -> str:
    raw = getattr(question_type, "value", question_type)
    return str(raw or "").strip().lower()


def _normalize_current(taxonomy: SkillTaxonomy, raw_ids) -> tuple[list[str], list[str]]:
    """Chuẩn hóa nhãn hiện có; trả về (id hợp lệ, id lạ bị loại)."""
    valid: list[str] = []
    unknown: list[str] = []
    for raw in raw_ids or []:
        if not isinstance(raw, str) or not raw.strip():
            continue
        sid = taxonomy.normalize_skill_id(raw)
        if sid is None:
            unknown.append(raw.strip())
        elif sid not in valid:
            valid.append(sid)
    return valid, unknown


def audit_question(
    question_id: int,
    question_text: str,
    question_type,
    current_skill_ids,
    *,
    taxonomy: SkillTaxonomy | None = None,
) -> QuestionTagAudit:
    """Soi nhãn kỹ năng của một câu hỏi dựa trên bằng chứng văn bản.

    - Nhãn công nghệ chỉ được giữ/thêm khi xuất hiện trong câu hỏi.
    - Nhãn kỹ năng mềm được giữ cho câu hỏi hành vi/tình huống,
      không tự thêm mới.
    - Id lạ (không có trong taxonomy) bị loại khỏi DB.
    """
    taxonomy = taxonomy or get_default_taxonomy()
    qtype = _normalize_type(question_type)
    current, unknown = _normalize_current(taxonomy, current_skill_ids)
    evidence = sorted({s.id for s in taxonomy.extract_skills_from_text(question_text or "")})

    keeps: list[str] = []
    dropped: list[str] = []
    for sid in current:
        text_ok = sid in evidence
        soft_ok = sid in SOFT_SKILL_IDS and qtype in SOFT_QUESTION_TYPES
        if text_ok or soft_ok:
            keeps.append(sid)
        else:
            dropped.append(sid)

    added = [sid for sid in evidence if sid not in keeps]
    return QuestionTagAudit(
        question_id=question_id,
        question_type=qtype,
        current=current,
        final=keeps + added,
        evidence=evidence,
        added=added,
        dropped=dropped,
        unknown_dropped=unknown,
    )


def build_tagging_prompt(question_text: str, taxonomy: SkillTaxonomy | None = None) -> str:
    """Prompt gợi ý nhãn bằng LLM — chỉ để tham khảo, không tự động ghi DB."""
    taxonomy = taxonomy or get_default_taxonomy()
    allowed = ", ".join(sorted(s.id for s in taxonomy.all_skills()))
    return (
        "Bạn là chuyên gia gắn nhãn kỹ năng cho ngân hàng câu hỏi phỏng vấn kỹ thuật.\n"
        "Chỉ được chọn nhãn từ danh sách id sau (không tự tạo id mới):\n"
        f"{allowed}\n\n"
        "Câu hỏi:\n"
        f"{question_text}\n\n"
        "Trả về JSON đúng định dạng {\"skill_ids\": [\"id1\", \"id2\"]}. "
        "Chỉ gắn những kỹ năng mà câu hỏi thực sự kiểm tra; nếu không chắc thì trả về danh sách rỗng."
    )
