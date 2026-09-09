from __future__ import annotations

from typing import Protocol


class WarehouseLookupPort(Protocol):
    async def warehouse_exists(self, code: str) -> bool:
        ...
