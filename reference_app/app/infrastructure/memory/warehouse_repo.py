from __future__ import annotations

from .state import MemoryState


class InMemoryWarehouseRepository:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def warehouse_exists(self, code: str) -> bool:
        return code in self._state.warehouses
