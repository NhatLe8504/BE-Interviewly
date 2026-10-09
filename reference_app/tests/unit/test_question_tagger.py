import httpx

from app.application.skills.question_tagger import (
    audit_question,
    suggest_skill_ids_with_llm,
)


def test_technical_label_without_text_evidence_is_dropped():
    """LOI #7: critical bug không được gán nhãn Java khi câu hỏi không nói tới Java."""
    audit = audit_question(
        19,
        "Hãy kể về một lần bạn gặp phải một critical bug trên production và các bước xử lý sự cố?",
        "behavioral",
        ["java", "problem-solving"],
    )
    assert audit.final == ["problem-solving"]
    assert audit.dropped == ["java"]


def test_slow_query_question_loses_dbms_guess():
    """Câu hỏi slow query không nói rõ DBMS thì không được gắn PostgreSQL."""
    audit = audit_question(
        20,
        "Bạn tiếp cận và tối ưu hóa một câu lệnh truy vấn cơ sở dữ liệu bị chậm (slow query) đang làm nghẽn API như thế nào?",
        "technical",
        ["sql", "postgresql", "rest-api"],
    )
    assert audit.final == []
    assert set(audit.dropped) == {"sql", "postgresql", "rest-api"}


def test_evidence_is_kept_and_added_without_js_inside_nextjs():
    audit = audit_question(
        22,
        "Làm thế nào để cải thiện Core Web Vitals cho một ứng dụng Next.js có kích thước lớn?",
        "technical",
        ["react", "javascript"],
    )
    assert audit.final == ["nextjs"]
    assert audit.added == ["nextjs"]
    assert set(audit.dropped) == {"react", "javascript"}


def test_soft_skill_is_kept_only_for_behavioral_questions():
    behavioral = audit_question(1, "Kể về một lần bạn bất đồng quan điểm với đồng nghiệp.", "behavioral", ["communication"])
    assert behavioral.final == ["communication"]

    technical = audit_question(2, "Giải thích cách mô hình hóa tài chính DCF.", "technical", ["communication"])
    assert technical.final == []
    assert technical.dropped == ["communication"]


def test_unknown_ids_are_removed_from_db():
    audit = audit_question(1, "Tối ưu câu lệnh SQL như thế nào?", "technical", ["java", "totally-made-up"])
    assert audit.unknown_dropped == ["totally-made-up"]
    assert audit.final == ["sql"]


def test_llm_suggestions_are_validated_against_taxonomy(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"skill_ids": ["java", "made-up", "Golang"]}'}}]}

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())

    ids = suggest_skill_ids_with_llm(
        "Câu hỏi bất kỳ",
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="test-model",
    )
    assert ids == ["java", "go"]
