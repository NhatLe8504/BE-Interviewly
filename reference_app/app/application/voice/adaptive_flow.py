from __future__ import annotations

import time
from typing import Any

from .turn_judge import TurnJudgment

_STAGE_FOR_SECTION = {
    "introduction": "warmup",
    "technical": "technical",
    "scenario": "technical",
    "system_design": "technical",
    "role_specific": "technical",
    "behavioral": "technical",
    "closing": "closing",
}
_STAGE_WEIGHTS = {"warmup": 1, "technical": 4, "closing": 1}
_FALLBACK_QUESTIONS = {
    "warmup": "Hãy giới thiệu ngắn gọn về bản thân, kinh nghiệm và lý do bạn quan tâm vị trí này.",
    "technical": "Hãy kể về một bài toán chuyên môn bạn đã giải quyết và cách kiểm chứng kết quả.",
    "closing": "Bạn còn thắc mắc gì về công việc hoặc phần trao đổi chuyên môn vừa rồi không?",
}
_FALLBACK_EN = {
    "warmup": "Please introduce yourself, your experience, and why this role interests you.",
    "technical": "Tell me about a technical challenge you solved and how you verified the outcome.",
    "closing": "Do you have any questions about the role or our technical discussion?",
}
_WARMUP_TOPICS = {
    "vi": (
        "Giới thiệu sơ qua về vai trò, kinh nghiệm và công cụ bạn thường dùng gần đây nhé?",
        "Điều gì khiến bạn quan tâm vị trí này? Bạn thấy điểm mạnh của mình là gì, "
        "và còn điểm nào bạn muốn cải thiện?",
    ),
    "en": (
        "Could you briefly describe your recent role, experience, and tools you use?",
        "What interests you about this role? What are your strengths, and what would you like to improve?",
    ),
}
_WARMUP_SIGNALS = {
    "vi": (
        ["Vai trò và kinh nghiệm làm việc ở mức khái quát", "Công cụ hoặc công nghệ thường dùng, chỉ cần nêu tên"],
        ["Lý do quan tâm vị trí ứng tuyển", "Điểm mạnh hoặc điều muốn cải thiện"],
    ),
    "en": (
        ["Brief overview of role and work experience", "Tools or technologies used, without implementation details"],
        ["Reason for interest in the role", "Strength or area for improvement"],
    ),
}
_COMPLETE = {"completed_covered", "completed_unresolved", "skipped_with_reason"}
_SKIP_PHRASES = (
    "bỏ qua câu", "qua câu mới", "qua câu tiếp", "chuyển câu", "chuyển sang câu", "skip this", "pass this",
)

_TECH_KEYWORDS = (
    "kiến trúc", "oop", "thuật toán", "database", "cơ sở dữ liệu",
    "api", "thread", "stream", "multithreading", "jvm", "garbage collection",
    "design pattern", "framework", "microservice", "latency", "sql", "nosql",
    "cache", "redis", "docker", "k8s", "kubernetes", "backend", "frontend",
    "collections", "generics", "concurrency", "deadlock",
)

_CANNOT_ANSWER_PHRASES = (
    "không biết", "em không biết", "mình không biết", "tôi không biết",
    "con này em không biết", "câu này em không biết", "chưa tìm hiểu",
    "chưa có kinh nghiệm", "chưa làm việc với", "chưa từng làm", "chưa từng dùng",
    "bỏ qua câu này", "bỏ qua câu hỏi", "qua câu tiếp", "chuyển câu", "chuyển qua câu",
    "chuyển sang câu", "em chịu", "chịu thôi", "i don't know", "dont know", "skip this",
    "pass this",
)


def is_candidate_cannot_answer(text: str) -> bool:
    clean = text.lower().strip()
    if not clean:
        return False
    if any(phrase in clean for phrase in _CANNOT_ANSWER_PHRASES):
        if len(clean) < 160:
            return True
        for phrase in _CANNOT_ANSWER_PHRASES:
            if clean.startswith(phrase) or f"xin lỗi {phrase}" in clean or f"dạ {phrase}" in clean:
                return True
    return False


def warmup_topic(item: dict[str, Any], language: str = "vi") -> str:
    question = str(item.get("question", "")).lower()
    strengths = item.get("id") == "warmup-strengths" or any(
        term in question for term in ("điểm mạnh", "điểm yếu", "strength", "weakness")
    )
    return _WARMUP_TOPICS["vi" if language == "vi" else "en"][int(strengths)]


def create_snapshot(script_items: list[dict[str, Any]], stages: list[str], duration_minutes: int, language: str = "vi") -> dict[str, Any]:
    active = [stage for stage in _STAGE_WEIGHTS if stage in stages] or ["technical"]
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(script_items):
        stage = _STAGE_FOR_SECTION.get(str(raw.get("section_type", "")).lower())
        if not raw.get("question_text"):
            continue
        question = str(raw["question_text"]).strip()
        if stage == "warmup":
            if any(term in question.lower() for term in _TECH_KEYWORDS):
                stage = "technical"
            else:
                continue
        if stage not in active:
            continue
        signals = [str(signal).strip()[:160] for signal in (raw.get("expected_signals") or [])[:6] if str(signal).strip()]
        items.append({
            "id": f"jd-{index}", "stage": stage, "question": question,
            "type": str(raw.get("section_type", "technical")),
            "signals": signals or ["Answer addresses the question with a concrete example"],
            "required": raw.get("required", True) is not False, "status": "not_asked",
            "evidence": {}, "answers": [], "probes": 0,
        })
    if "warmup" in active:
        items.append({
            "id": "opening-introduction", "stage": "warmup",
            "question": _WARMUP_TOPICS["vi" if language == "vi" else "en"][0],
            "type": "introduction", "signals": _WARMUP_SIGNALS["vi" if language == "vi" else "en"][0][:],
            "required": True, "status": "not_asked", "evidence": {}, "answers": [], "probes": 0,
        })
        items.append({
            "id": "warmup-strengths", "stage": "warmup",
            "question": _WARMUP_TOPICS["vi" if language == "vi" else "en"][1],
            "type": "introduction", "signals": _WARMUP_SIGNALS["vi" if language == "vi" else "en"][1][:],
            "required": True, "status": "not_asked", "evidence": {}, "answers": [], "probes": 0,
        })
    for stage in active:
        if not any(item["stage"] == stage for item in items):
            items.append({
                "id": f"fallback-{stage}", "stage": stage,
                "question": (_FALLBACK_QUESTIONS if language == "vi" else _FALLBACK_EN)[stage], "type": stage,
                "signals": ["Answer addresses the question with a concrete example"],
                "required": True, "status": "not_asked", "evidence": {}, "answers": [], "probes": 0,
            })
    items.sort(key=lambda item: active.index(item["stage"]))
    weight_total = sum(_STAGE_WEIGHTS[stage] for stage in active)
    total_seconds = max(5, int(duration_minutes)) * 60
    budgets = {stage: total_seconds * _STAGE_WEIGHTS[stage] // weight_total for stage in active}
    budgets[active[-1]] += total_seconds - sum(budgets.values())
    return {
        "items": items, "stages": active, "stage_index": 0, "stage_version": 1,
        "duration_minutes": max(5, int(duration_minutes)),
        "budgets": budgets,
        "elapsed": 0.0, "elapsed_by_stage": {}, "active_since": None, "pending": None,
        "last_turn": 0, "last_received_turn": 0, "current_item": None,
    }


def active_elapsed(flow: dict[str, Any]) -> float:
    started = flow.get("active_since")
    return float(flow.get("elapsed", 0)) + (max(0, time.time() - started) if started else 0)


def resume(flow: dict[str, Any]) -> None:
    if flow.get("active_since") is None:
        flow["active_since"] = time.time()


def pause(flow: dict[str, Any]) -> None:
    flow["elapsed"] = active_elapsed(flow)
    flow["active_since"] = None


def current_item(flow: dict[str, Any]) -> dict[str, Any] | None:
    stage = flow["stages"][flow["stage_index"]]
    item_id = flow.get("current_item")
    if item_id:
        for item in flow["items"]:
            if item["id"] == item_id and item["stage"] == stage and item["status"] not in _COMPLETE:
                return item
    for item in flow["items"]:
        if item["stage"] == stage and item["status"] not in _COMPLETE:
            flow["current_item"] = item["id"]
            return item
    flow["current_item"] = None
    return None


def stage_progress(flow: dict[str, Any]) -> dict[str, Any]:
    stage = flow["stages"][flow["stage_index"]]
    items = [item for item in flow["items"] if item["stage"] == stage]
    completed = sum(item["status"] in _COMPLETE for item in items)
    discussed = sum(
        item["status"] in _COMPLETE or (
            bool(item.get("answers")) if stage == "technical" else
            item.get("discussed", bool(item.get("answers")))
        ) for item in items
    )
    remaining = sum(item["required"] and item["status"] not in _COMPLETE for item in items)
    return {
        "stage": stage, "completed": completed, "discussed": discussed, "total": len(items),
        "ready": remaining == 0, "remaining_required": remaining,
        "elapsed_seconds": int(active_elapsed(flow)),
        "total_elapsed_seconds": int(sum(flow.get("elapsed_by_stage", {}).values()) + active_elapsed(flow)),
        "target_seconds": flow["budgets"][stage], "item_id": flow.get("current_item"),
        "stage_version": flow["stage_version"], "pending": flow.get("pending"),
    }


def apply_judgment(flow: dict[str, Any], judgment: TurnJudgment, turn_id: int, answer: str) -> tuple[str, str | None]:
    item = current_item(flow)
    if item is None or turn_id <= flow["last_turn"]:
        return "ignore", None
    flow["last_turn"] = turn_id
    item["status"] = "probing"
    item.setdefault("answers", []).append({"turn_id": turn_id, "text": answer[:2000]})
    for signal in item["signals"]:
        score = judgment.signal_scores.get(signal)
        if score is None:
            continue
        previous = item["evidence"].get(signal, {})
        if score >= previous.get("score", -1):
            item["evidence"][signal] = {"score": score, "turn_ids": list(dict.fromkeys(previous.get("turn_ids", []) + [turn_id]))}
    threshold = 1.0 if item["stage"] == "warmup" else 1.8
    missing = [signal for signal in item["signals"] if item["evidence"].get(signal, {}).get("score", 0) < threshold]
    cannot_answer = judgment.disposition == "cannot_answer" or is_candidate_cannot_answer(answer)
    item["discussed"] = item.get("discussed", False) or (
        judgment.disposition in ("responsive", "needs_clarification") or
        any(value.get("score", 0) >= 1 for value in item["evidence"].values()) or
        (judgment.source != "jev" and len(answer.split()) >= 4)
    )
    if item["stage"] == "warmup":
        skip_requested = (
            any(phrase in answer.lower() for phrase in _SKIP_PHRASES) and
            not any(phrase in answer.lower() for phrase in ("không bỏ qua", "đừng bỏ qua", "don't skip"))
        )
        if not missing and judgment.source == "jev":
            item["status"] = "completed_covered"
        elif skip_requested or item["probes"] >= 2:
            item["status"] = "completed_unresolved"
            item["reason"] = "judge_unavailable" if judgment.source != "jev" else "warmup_probe_limit_or_skip"
        else:
            item["probes"] += 1
            return "probe_warmup", missing[0] if missing else item["signals"][0]
        flow["current_item"] = None
        return "next_item", None
    if not missing and judgment.source == "jev":
        item["status"] = "completed_covered"
    elif item["probes"] >= 2 or cannot_answer or judgment.explicitly_no_more:
        item["status"] = "completed_unresolved"
        item["reason"] = "probe_limit_or_candidate_cannot_answer" if judgment.source == "jev" else "judge_unavailable"
    else:
        item["probes"] += 1
        return "probe", missing[0] if missing else item["signals"][0]
    flow["current_item"] = None
    return "next_item", None


def skip_remaining(flow: dict[str, Any], reason: str) -> None:
    stage = flow["stages"][flow["stage_index"]]
    for item in flow["items"]:
        if item["stage"] == stage and item["status"] not in _COMPLETE:
            item["status"] = "skipped_with_reason"
            item["reason"] = reason
    flow["current_item"] = None


def advance_stage(flow: dict[str, Any]) -> bool:
    if flow["stage_index"] >= len(flow["stages"]) - 1:
        return False
    flow.setdefault("elapsed_by_stage", {})[flow["stages"][flow["stage_index"]]] = active_elapsed(flow)
    flow["stage_index"] += 1
    flow["stage_version"] += 1
    flow["elapsed"] = 0.0
    flow["active_since"] = time.time()
    flow["pending"] = None
    flow["current_item"] = None
    return True
