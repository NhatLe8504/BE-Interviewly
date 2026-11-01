from __future__ import annotations

from typing import Any


def answer_groups(turns: list[Any], flow_snapshot: dict[str, Any] | None) -> list[list[Any]]:
    answered = {
        turn.turn_number: turn for turn in turns
        if turn.transcribed_text or (
            getattr(turn.speaker, "value", turn.speaker) == "candidate" and turn.message_text
        )
    }
    if flow_snapshot is None:
        return [[turn] for turn in turns if turn.turn_number in answered]

    groups: list[list[Any]] = []
    seen: set[int] = set()
    for item in flow_snapshot.get("items", []):
        if item.get("stage") != "technical":
            continue
        group = []
        for answer in item.get("answers", []):
            turn_number = answer.get("turn_id")
            if type(turn_number) is int and turn_number in answered and turn_number not in seen:
                group.append(answered[turn_number])
                seen.add(turn_number)
        if group:
            groups.append(group)
    return groups
