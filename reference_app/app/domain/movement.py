from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .errors import DomainValidationError


class MovementType(str, Enum):
    IN = "IN"
    OUT = "OUT"


class MovementStatus(str, Enum):
    DRAFT = "DRAFT"


@dataclass(frozen=True)
class MovementLine:
    sku: str
    quantity: int
    unit_price: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.sku or not self.sku.strip():
            raise DomainValidationError("line sku must not be empty")
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be > 0")
        if self.unit_price < 0:
            raise DomainValidationError("unit_price must be >= 0")

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class StockMovement:
    id: int
    warehouse_code: str
    movement_type: MovementType
    status: MovementStatus
    lines: tuple
    created_at: datetime

    @classmethod
    def create_draft(
        cls,
        *,
        id: int,
        warehouse_code: str,
        movement_type: MovementType,
        lines: list,
        created_at: datetime,
    ) -> "StockMovement":
        if not warehouse_code or not warehouse_code.strip():
            raise DomainValidationError("warehouse_code must not be empty")
        if not lines:
            raise DomainValidationError("movement must have at least one line")
        return cls(
            id=id,
            warehouse_code=warehouse_code,
            movement_type=movement_type,
            status=MovementStatus.DRAFT,
            lines=tuple(lines),
            created_at=created_at,
        )

    @property
    def total_amount(self) -> Decimal:
        total = Decimal("0")
        for line in self.lines:
            total += line.line_total
        return total
