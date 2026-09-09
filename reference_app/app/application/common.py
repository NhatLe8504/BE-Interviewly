from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Protocol, TypeVar


@dataclass(frozen=True)
class PageRequest:
    page: int = 1
    size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= self.size <= 100:
            raise ValueError("size must be between 1 and 100")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


T = TypeVar("T")


@dataclass(frozen=True)
class PageResult(Generic[T]):
    items: tuple
    total: int


class ClockPort(Protocol):
    def now(self) -> datetime:
        ...
