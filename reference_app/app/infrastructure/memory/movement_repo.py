from __future__ import annotations

from dataclasses import replace

from ...domain.movement import StockMovement
from .state import MemoryState


class InMemoryMovementRepository:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def add(self, movement: StockMovement) -> StockMovement:
        self._state.movement_seq += 1
        stored = replace(movement, id=self._state.movement_seq)
        self._state.movements[stored.id] = stored
        return stored

    async def list(self) -> tuple:
        ordered = sorted(self._state.movements.values(), key=lambda m: m.id)
        return tuple(ordered)
