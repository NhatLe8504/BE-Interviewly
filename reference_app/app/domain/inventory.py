from __future__ import annotations

from dataclasses import dataclass

from .errors import DomainValidationError


@dataclass(frozen=True)
class Warehouse:
    code: str
    name: str

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise DomainValidationError("warehouse code must not be empty")
        if not self.name or not self.name.strip():
            raise DomainValidationError("warehouse name must not be empty")
