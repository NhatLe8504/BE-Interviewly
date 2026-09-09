from __future__ import annotations


def test_health_ok(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_list_products_returns_seeded_page(client) -> None:
    body = client.get("/api/v1/products").json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert {item["sku"] for item in body["items"]} == {"SKU-001", "SKU-002", "SKU-003"}


def test_list_products_search_and_paging(client) -> None:
    body = client.get("/api/v1/products", params={"search": "widget"}).json()
    assert body["total"] == 2
    page2 = client.get("/api/v1/products", params={"page": 2, "size": 2}).json()
    assert (page2["total"], len(page2["items"])) == (3, 1)


def test_get_product_and_404(client) -> None:
    assert client.get("/api/v1/products/SKU-001").status_code == 200
    missing = client.get("/api/v1/products/NOPE")
    assert missing.status_code == 404
    assert "detail" in missing.json()


def test_openapi_exposes_products(client) -> None:
    spec = client.get("/openapi.json").json()
    assert "/api/v1/products" in spec["paths"]
