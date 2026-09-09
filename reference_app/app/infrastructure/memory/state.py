from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ...domain.catalog import Product
from ...domain.inventory import Warehouse


@dataclass
class MemoryState:
    products: dict = field(default_factory=dict)
    warehouses: dict = field(default_factory=dict)
    movements: dict = field(default_factory=dict)
    movement_seq: int = 0

    def reset(self) -> None:
        self.products.clear()
        self.warehouses.clear()
        self.movements.clear()
        self.movement_seq = 0

    def seed(self) -> None:
        self.reset()
        for product in (
            Product(sku="SKU-001", name="Widget A", unit="pcs", price=Decimal("12.50")),
            Product(sku="SKU-002", name="Widget B", unit="pcs", price=Decimal("7.99")),
            Product(sku="SKU-003", name="Gadget C", unit="box", price=Decimal("25.00")),
        ):
            self.products[product.sku] = product
        for warehouse in (
            Warehouse(code="WH-01", name="Kho chinh"),
            Warehouse(code="WH-02", name="Kho phu"),
        ):
            self.warehouses[warehouse.code] = warehouse
