def answer_framework(question_type: str | None) -> str:
    kind = getattr(question_type, "value", question_type)
    return {
        "behavioral": "star", "technical": "technical", "system_design": "technical",
        "role_specific": "technical", "scenario": "situational", "situational": "situational",
    }.get(str(kind or "").lower(), "generic")


def hint_fallback(framework: str, language: str = "vi") -> str:
    hints = {
        "vi": {
            "star": "Hãy kể trải nghiệm thực tế: bối cảnh, trách nhiệm, hành động cụ thể và kết quả.",
            "technical": "Hãy nêu cách tiếp cận, lý do lựa chọn, giới hạn và cách kiểm chứng.",
            "situational": "Hãy xác định ràng buộc, so sánh phương án, chọn bước tiếp theo và nêu rủi ro.",
            "generic": "Hãy làm rõ yêu cầu, nêu lập luận và ví dụ phù hợp.",
        },
        "en": {
            "star": "Describe a real experience: context, responsibility, actions and outcome.",
            "technical": "Explain your approach, reasoning, trade-offs and verification.",
            "situational": "Identify constraints, compare options, decide and discuss risks.",
            "generic": "Clarify the question, explain your reasoning and give an example.",
        },
    }
    return hints["vi" if language == "vi" else "en"][framework]
