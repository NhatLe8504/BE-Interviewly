from __future__ import annotations

from typing import Any, Protocol


class CompanyBrandingLookup(Protocol):
    async def lookup(self, job: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]: ...
