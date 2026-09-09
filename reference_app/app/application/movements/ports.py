from __future__ import annotations

from typing import Protocol

from ...domain.movement import StockMovement


class MovementRepositoryPort(Protocol):
    async def add(self, movement: StockMovement) -> StockMovement:
        ...

    async def list(self) -> tuple:
        ...
