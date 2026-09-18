from __future__ import annotations

import pytest

from app.application.interview.commands import StageConfigCommand
from app.application.interview.session_plan import (
    MAX_SESSION_TURNS,
    default_stage_configs,
    validate_stage_configs,
)
from app.domain.errors import DomainValidationError


def config(
    stage_key: str,
    source_mode: str = "auto_random",
    min_turns: int = 1,
    max_turns: int = 1,
    selected_question_ids: list[int] | None = None,
) -> StageConfigCommand:
    return StageConfigCommand(
        stage_key=stage_key,
        source_mode=source_mode,
        min_turns=min_turns,
        max_turns=max_turns,
        selected_question_ids=selected_question_ids,
    )


def test_default_plan_stays_within_session_turn_limit() -> None:
    configs = validate_stage_configs(default_stage_configs())

    assert sum(item.max_turns for item in configs) == MAX_SESSION_TURNS


@pytest.mark.parametrize(
    ("configs", "message"),
    [
        ([config("unknown")], "unsupported stage_key"),
        ([config("warmup"), config("warmup")], "duplicate stage_key"),
        ([config("warmup", source_mode="invalid")], "unsupported source_mode"),
        ([config("warmup", min_turns=2, max_turns=1)], "invalid turn range"),
        ([config("warmup", max_turns=4)], "max_turns cannot exceed"),
        ([config("warmup", source_mode="auto_random", selected_question_ids=[1])], "auto_random stage"),
        ([config("technical", source_mode="manual", max_turns=2, selected_question_ids=[1])], "manual stage"),
        ([config("technical", source_mode="mixed")], "mixed stage"),
    ],
)
def test_invalid_stage_policy_is_rejected(
    configs: list[StageConfigCommand], message: str,
) -> None:
    with pytest.raises(DomainValidationError, match=message):
        validate_stage_configs(configs)


def test_question_cannot_be_assigned_to_multiple_stages() -> None:
    with pytest.raises(DomainValidationError, match="already assigned"):
        validate_stage_configs(
            [
                config("warmup", source_mode="manual", selected_question_ids=[11]),
                config("technical", source_mode="manual", selected_question_ids=[11]),
            ],
        )


def test_valid_mixed_plan_accepts_preselected_question_and_random_backfill() -> None:
    configs = validate_stage_configs(
        [
            config("warmup", source_mode="auto_random"),
            config("technical", source_mode="mixed", max_turns=2, selected_question_ids=[11]),
            config("closing", source_mode="manual", selected_question_ids=[12]),
        ],
    )

    assert configs[1].selected_question_ids == [11]


def test_session_turn_limit_is_enforced() -> None:
    with pytest.raises(DomainValidationError, match="cannot exceed"):
        validate_stage_configs(
            [
                config("warmup", max_turns=2),
                config("technical", max_turns=2),
                config("closing", max_turns=2),
            ],
        )
