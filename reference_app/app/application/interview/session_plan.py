from __future__ import annotations

from collections.abc import Iterable

from ...domain.errors import DomainValidationError
from .commands import StageConfigCommand


ALLOWED_STAGE_KEYS = ("warmup", "technical", "closing")
ALLOWED_SOURCE_MODES = ("auto_random", "manual", "mixed")
MAX_STAGE_TURNS = 3
MAX_SESSION_TURNS = 5


def default_stage_configs() -> list[StageConfigCommand]:
    return [
        StageConfigCommand(
            stage_key="warmup",
            source_mode="auto_random",
            min_turns=1,
            max_turns=1,
        ),
        StageConfigCommand(
            stage_key="technical",
            source_mode="auto_random",
            min_turns=2,
            max_turns=3,
        ),
        StageConfigCommand(
            stage_key="closing",
            source_mode="auto_random",
            min_turns=1,
            max_turns=1,
        ),
    ]


def validate_stage_configs(
    stage_configs: Iterable[StageConfigCommand],
) -> list[StageConfigCommand]:
    configs = list(stage_configs)
    if not configs:
        raise DomainValidationError("at least one stage config is required")

    seen_stages: set[str] = set()
    selected_question_owners: dict[int, str] = {}
    total_turns = 0

    for config in configs:
        if config.stage_key not in ALLOWED_STAGE_KEYS:
            raise DomainValidationError(f"unsupported stage_key: {config.stage_key}")
        if config.stage_key in seen_stages:
            raise DomainValidationError(f"duplicate stage_key: {config.stage_key}")
        seen_stages.add(config.stage_key)

        if config.source_mode not in ALLOWED_SOURCE_MODES:
            raise DomainValidationError(f"unsupported source_mode: {config.source_mode}")
        if config.min_turns < 1 or config.max_turns < config.min_turns:
            raise DomainValidationError(f"invalid turn range for stage: {config.stage_key}")
        if config.max_turns > MAX_STAGE_TURNS:
            raise DomainValidationError(
                f"max_turns cannot exceed {MAX_STAGE_TURNS} for stage: {config.stage_key}"
            )

        selected_question_ids = config.selected_question_ids or []
        if config.source_mode == "auto_random" and selected_question_ids:
            raise DomainValidationError(
                f"auto_random stage cannot contain selected questions: {config.stage_key}"
            )
        if config.source_mode == "manual" and len(selected_question_ids) < config.max_turns:
            raise DomainValidationError(
                f"manual stage requires at least {config.max_turns} selected questions: {config.stage_key}"
            )
        if config.source_mode == "mixed" and not selected_question_ids:
            raise DomainValidationError(
                f"mixed stage requires at least one selected question: {config.stage_key}"
            )

        for question_id in selected_question_ids:
            if not isinstance(question_id, int) or question_id <= 0:
                raise DomainValidationError("selected question ids must be positive integers")
            if question_id in selected_question_owners:
                previous_stage = selected_question_owners[question_id]
                raise DomainValidationError(
                    f"question {question_id} is already assigned to stage: {previous_stage}"
                )
            selected_question_owners[question_id] = config.stage_key

        total_turns += config.max_turns

    if total_turns > MAX_SESSION_TURNS:
        raise DomainValidationError(
            f"session cannot exceed {MAX_SESSION_TURNS} total turns"
        )

    return configs
