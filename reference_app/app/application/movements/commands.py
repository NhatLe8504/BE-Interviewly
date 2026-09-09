from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...domain.movement import MovementType


@dataclass(frozen=True)
class MovementLineInput:
    sku: str
    quantity: int
    unit_price: Decimal = Decimal("0")


@dataclass(frozen=True)
class CreateMovementCommand:
    warehouse_code: str
    movement_type: MovementType
    lines: tuple
