from __future__ import annotations

from app.application.voice.adaptive_flow import (
    advance_stage,
    apply_judgment,
    create_snapshot,
    current_item,
    skip_remaining,
    stage_progress,
    warmup_topic,
)
from app.application.voice.turn_judge import TurnJudgment
from app.infrastructure.llm.jev_turn_adapter import JevInterviewTurnJudge


def _script() -> list[dict]:
    return [
        {"section_type": "introduction", "question_text": "Giới thiệu bản thân và kinh nghiệm của bạn?",
         "expected_signals": ["experience"]},
        {"section_type": "technical", "question_text": "Bạn dùng cache như thế nào?",
         "expected_signals": ["cache", "measurement"]},
        {"section_type": "scenario", "question_text": "Bạn xử lý outage thế nào?",
         "expected_signals": ["incident"]},
        {"section_type": "closing", "question_text": "Bạn còn câu hỏi nào cho chúng tôi?"},
    ]


def test_snapshot_preserves_jd_stage_order_and_one_four_one_budget() -> None:
    flow = create_snapshot(_script(), ["warmup", "technical", "closing"], 60)
    assert [item["stage"] for item in flow["items"]] == [
        "warmup", "warmup", "technical", "technical", "closing",
    ]
    assert flow["budgets"] == {"warmup": 600, "technical": 2400, "closing": 600}
    assert current_item(flow)["question"].startswith("Giới thiệu")
    assert flow["stage_index"] == 0


def test_warmup_retains_introduction_and_strengths_when_jd_has_only_technical_questions() -> None:
    flow = create_snapshot([
        {"section_type": "technical", "question_text": "Bạn giải thích Docker thế nào?"},
    ], ["warmup", "technical", "closing"], 30)
    warmup = [item for item in flow["items"] if item["stage"] == "warmup"]
    assert [item["id"] for item in warmup] == ["opening-introduction", "warmup-strengths"]
    assert all(item["required"] for item in warmup)
    assert not stage_progress(flow)["ready"]


def test_follow_up_uses_accumulated_evidence_before_next_item() -> None:
    flow = create_snapshot(_script(), ["technical"], 30)
    first = current_item(flow)
    action, target = apply_judgment(
        flow, TurnJudgment({"cache": 2.4, "measurement": 0.2}, source="jev"), 3,
        "Tôi dùng Redis cache-aside.",
    )
    assert (action, target) == ("probe", "measurement")
    assert stage_progress(flow)["completed"] == 0
    assert stage_progress(flow)["discussed"] == 1
    action, target = apply_judgment(
        flow, TurnJudgment({"cache": 2.4, "measurement": 2.5}, source="jev"), 4,
        "Tôi đo p95 latency trước và sau.",
    )
    assert (action, target) == ("next_item", None)
    assert first["status"] == "completed_covered"
    assert [answer["turn_id"] for answer in first["answers"]] == [3, 4]
    assert first["evidence"]["cache"]["turn_ids"] == [3, 4]
    assert not stage_progress(flow)["ready"]
    assert flow["stage_index"] == 0


def test_fallback_is_bounded_and_skipping_requires_explicit_reason() -> None:
    flow = create_snapshot([], ["technical", "closing"], 30)
    for turn_id in (1, 2, 3):
        apply_judgment(flow, TurnJudgment(), turn_id, "Tôi chưa rõ.")
    assert flow["items"][0]["status"] == "completed_unresolved"
    assert flow["items"][0]["reason"] == "judge_unavailable"
    assert stage_progress(flow)["ready"]
    assert flow["stage_index"] == 0
    assert advance_stage(flow)
    skip_remaining(flow, "candidate_confirmed_overtime_skip")
    assert flow["items"][1]["reason"] == "candidate_confirmed_overtime_skip"


def test_dense_jd_introduction_does_not_turn_warmup_into_a_technical_probe() -> None:
    flow = create_snapshot([{
        "section_type": "introduction",
        "question_text": "Giới thiệu dự án quan trọng, vai trò, công nghệ chủ chốt và kết quả đạt được?",
        "expected_signals": ["Thiết kế pipeline CI/CD", "Tối ưu latency"],
    }], ["warmup", "technical"], 30)
    warmup = [item for item in flow["items"] if item["stage"] == "warmup"]
    assert [item["id"] for item in warmup] == ["opening-introduction", "warmup-strengths"]
    assert "dự án quan trọng" not in warmup[0]["question"]
    assert len(warmup[0]["signals"]) == 2


def test_saved_warmup_question_is_normalized_when_resuming_an_old_session() -> None:
    legacy_item = {"id": "jd-0", "question": "Giới thiệu dự án, CI/CD và tối ưu latency?"}
    assert "kinh nghiệm" in warmup_topic(legacy_item)
    assert "CI/CD" not in warmup_topic(legacy_item)


def test_warmup_counts_a_brief_answer_only_when_both_general_signals_are_covered() -> None:
    flow = create_snapshot(_script(), ["warmup", "technical"], 30)
    first = current_item(flow)
    assert apply_judgment(
        flow, TurnJudgment({signal: 1.0 for signal in first["signals"]},
                           disposition="responsive", source="jev"), 2,
        "Em làm Software Engineer, thường dùng Java và đã có hai năm kinh nghiệm.",
    ) == ("next_item", None)
    assert first["status"] == "completed_covered"
    assert stage_progress(flow)["completed"] == 1
    assert stage_progress(flow)["discussed"] == 1
    assert not stage_progress(flow)["ready"]


def test_warmup_off_topic_answer_is_probed_before_bounded_unresolved_completion() -> None:
    flow = create_snapshot([], ["warmup", "technical"], 30)
    first = current_item(flow)
    assert apply_judgment(flow, TurnJudgment(disposition="off_topic", source="jev"), 2, "Em nghe không rõ.") == (
        "probe_warmup", first["signals"][0],
    )
    assert stage_progress(flow)["discussed"] == 0
    assert apply_judgment(flow, TurnJudgment(disposition="off_topic", source="jev"), 4, "Vẫn chưa rõ ạ.") == (
        "probe_warmup", first["signals"][0],
    )
    assert stage_progress(flow)["completed"] == 0
    assert apply_judgment(flow, TurnJudgment(disposition="off_topic", source="jev"), 6, "Em chưa hiểu ạ.") == (
        "next_item", None,
    )
    assert first["status"] == "completed_unresolved"
    assert stage_progress(flow)["completed"] == 1


def test_warmup_no_then_weakness_requires_a_follow_up_on_motivation() -> None:
    flow = create_snapshot([], ["warmup", "technical"], 30)
    first = current_item(flow)
    apply_judgment(flow, TurnJudgment({signal: 1.0 for signal in first["signals"]}, source="jev"),
                   2, "Em làm backend hai năm và dùng Java.")
    strengths = current_item(flow)
    motivation, development = strengths["signals"]

    assert apply_judgment(
        flow, TurnJudgment(disposition="cannot_answer", source="jev"), 4, "Không",
    ) == ("probe_warmup", motivation)
    assert apply_judgment(
        flow, TurnJudgment({motivation: 0.0, development: 1.0},
                           disposition="needs_clarification", source="jev"), 6,
        "Điểm yếu của em là em hơi run.",
    ) == ("probe_warmup", motivation)
    assert strengths["status"] == "probing"
    assert stage_progress(flow)["completed"] == 1
    assert not stage_progress(flow)["ready"]
    assert apply_judgment(
        flow, TurnJudgment({motivation: 1.0}, disposition="responsive", source="jev"), 8,
        "Em muốn phát triển thêm ở vị trí này.",
    ) == ("next_item", None)
    assert strengths["status"] == "completed_covered"
    assert stage_progress(flow)["ready"]


def test_explicit_warmup_skip_still_moves_to_next_topic() -> None:
    flow = create_snapshot([], ["warmup", "technical"], 30)
    first = current_item(flow)
    assert apply_judgment(flow, TurnJudgment(disposition="cannot_answer", source="jev"), 2,
                          "Em không biết, xin qua câu mới.") == ("next_item", None)
    assert first["status"] == "completed_unresolved"
    assert current_item(flow)["id"] == "warmup-strengths"


def test_old_generated_focuses_cannot_block_technical_progress() -> None:
    question = "Trình bày OOP, Collections và Stream API trong dự án của bạn."
    flow = create_snapshot([{"section_type": "technical", "question_text": question,
                             "expected_signals": ["Depth of technical explanation"]}], ["technical"], 30)
    item = current_item(flow)
    item["focuses"] = ["Thiết kế OOP", "Lựa chọn Collections", "Sử dụng Stream API"]
    item["focus_index"] = 0
    assert apply_judgment(
        flow, TurnJudgment({"Depth of technical explanation": 2.5}, source="jev"), 1,
        "Tôi áp dụng OOP và chọn Collections theo bài toán.",
    ) == ("next_item", None)
    assert item["question"] == question
    assert stage_progress(flow)["completed"] == 1
    assert stage_progress(flow)["discussed"] == 1


def test_technical_progress_shows_discussed_topic_before_all_signals_are_covered() -> None:
    flow = create_snapshot([
        {"section_type": "technical", "question_text": f"Câu hỏi {index}?",
         "expected_signals": ["Cách làm", "Kết quả"]}
        for index in range(8)
    ], ["technical"], 30)
    assert apply_judgment(
        flow, TurnJudgment({"Cách làm": 2.2, "Kết quả": 0.4},
                           disposition="needs_clarification", source="jev"), 1,
        "Em đã mô tả cách làm nhưng chưa có kết quả cụ thể.",
    ) == ("probe", "Kết quả")
    assert stage_progress(flow)["completed"] == 0
    assert stage_progress(flow)["discussed"] == 1
    assert stage_progress(flow)["total"] == 8
    assert apply_judgment(
        flow, TurnJudgment({"Kết quả": 2.1}, disposition="responsive", source="jev"), 2,
        "Kết quả là thời gian phản hồi giảm 20 phần trăm.",
    ) == ("next_item", None)
    assert stage_progress(flow)["completed"] == 1


def test_technical_progress_records_an_attempt_even_when_jev_is_uncertain() -> None:
    flow = create_snapshot([{"section_type": "technical", "question_text": "Bạn từng dùng Redis ra sao?"}],
                           ["technical"], 30)
    assert apply_judgment(flow, TurnJudgment(disposition="off_topic", source="jev"), 1,
                          "Em có dùng Redis nhưng bản ghi âm bị sai.")[0] == "probe"
    assert stage_progress(flow)["discussed"] == 1
    assert stage_progress(flow)["completed"] == 0


def test_jev_turn_judge_uses_typed_system_one_answers() -> None:
    judge = JevInterviewTurnJudge("test_real_key_123456", "https://api.typesafe.ai/v1/systemone", "jev-latest")
    captured: list[dict] = []

    def respond(payload: dict) -> dict:
        captured.append(payload)
        return {"answers": {
            "signal_0": {"type": "score", "score": 2.5, "confidence": 0.9},
            "disposition": {"type": "choice", "choice": "responsive", "confidence": 0.8},
            "no_more": {"type": "noul", "noul": 0.1},
        }}

    judge.client._post = respond
    result = judge.judge("Bạn dùng cache thế nào?", ["cache"], {}, "Redis", [])
    assert result.signal_scores == {"cache": 2.5}
    assert result.source == "jev"
    assert captured[0]["questions"]["signal_0"]["type"] == "score"
    assert captured[0]["questions"]["disposition"]["type"] == "choice"
    assert captured[0]["questions"]["no_more"]["type"] == "noul"
    assert "instructions" in captured[0]["questions"]["disposition"]

    judge.client._post = lambda _: {"answers": {"signal_0": {"score": 2.0}}}
    assert judge.judge("Question", ["cache"], {}, "Answer", []).source == "fallback"
