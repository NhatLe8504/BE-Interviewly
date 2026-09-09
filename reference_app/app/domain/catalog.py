from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .errors import DomainValidationError


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit: str = "pcs"
    price: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.sku or not self.sku.strip():
            raise DomainValidationError("sku must not be empty")
        if not self.name or not self.name.strip():
            raise DomainValidationError("name must not be empty")
        if self.price < 0:
            raise DomainValidationError("price must be >= 0")
