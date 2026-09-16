from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateModerationCommand:
    target_type: str
    action: str
    target_id: int | None = None
    reason: str | None = None
