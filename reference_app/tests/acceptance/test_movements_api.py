from __future__ import annotations


def payload(**overrides):
    body = {
        "warehouse_code": "WH-01",
        "movement_type": "IN",
        "lines": [{"sku": "SKU-001", "quantity": 2, "unit_price": "10.50"}],
    }
    body.update(overrides)
    return body


def test_create_movement_returns_201_with_location(client) -> None:
    response = client.post("/api/v1/movements", json=payload())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["total_amount"] == 21.0
    assert response.headers["Location"] == f"/api/v1/movements/{body['id']}"


def test_create_movement_unknown_warehouse_404(client) -> None:
    response = client.post("/api/v1/movements", json=payload(warehouse_code="WH-99"))
    assert response.status_code == 404


def test_create_movement_unknown_product_404(client) -> None:
    bad = payload()
    bad["lines"] = [{"sku": "NOPE", "quantity": 1}]
    assert client.post("/api/v1/movements", json=bad).status_code == 404


def test_create_movement_rejects_zero_quantity_422(client) -> None:
    bad = payload()
    bad["lines"] = [{"sku": "SKU-001", "quantity": 0}]
    assert client.post("/api/v1/movements", json=bad).status_code == 422


def test_create_movement_rejects_empty_lines_422(client) -> None:
    bad = payload(lines=[])
    assert client.post("/api/v1/movements", json=bad).status_code == 422


def test_list_and_get_movements(client) -> None:
    created = client.post("/api/v1/movements", json=payload()).json()
    listed = client.get("/api/v1/movements").json()
    assert len(listed) == 1
    fetched = client.get(f"/api/v1/movements/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert client.get("/api/v1/movements/999").status_code == 404
