# BE-Interviewly - Huong dan cho agent (WMS Lite, Unit 1-2)

> BE chay kien truc WMS Lite: Clean Architecture + N-layer.
> Code hien tai chi giai quyet Unit 1 (query san pham) va Unit 2 (tao phieu kho DRAFT).
> Moi module dang ton tai deu chay duoc - KHONG tao lop rong cho tinh nang tuong lai.

## 1. Cay thu muc

```text
reference_app/
|-- requirements.txt
|-- app/
|   |-- domain/            catalog.py, inventory.py, movement.py, errors.py
|   |-- application/
|   |   |-- common.py      PageRequest, PageResult, ClockPort
|   |   |-- container.py   ServiceContainer
|   |   |-- products/      ports.py (ProductQueryPort), query_service.py
|   |   |-- inventory/     ports.py (WarehouseLookupPort)
|   |   `-- movements/     commands.py, ports.py, service.py
|   |-- infrastructure/
|   |   |-- clock.py       SystemClock
|   |   `-- memory/        state.py, product_repo.py, warehouse_repo.py, movement_repo.py
|   |-- presentation/api/
|   |   |-- routers/       products.py, movements.py
|   |   |-- schemas/       product.py, movement.py (Pydantic v2)
|   |   |-- dependencies.py, error_handlers.py
|   |-- bootstrap.py       build_services() - composition root duy nhat
|   `-- main.py            create_app() + app
`-- tests/
    |-- unit/          invariant domain + use case voi fake port
    |-- integration/   memory adapter (loc, phan trang, seed, reset)
    |-- acceptance/    API: status, JSON, Location, 404/422, OpenAPI
    `-- architecture/  phan tich import, giu dependency rule
```

## 2. Dependency rule (bat buoc)

```text
HTTP -> presentation (router + Pydantic) -> application (use case + port) -> domain
infrastructure (memory adapter) --implements--> application port
bootstrap.py wires moi concrete object
```

- `domain`: chi stdlib. Cam import fastapi, pydantic, application, infrastructure, presentation.
- `application`: duoc import domain. Cam import fastapi, pydantic, presentation, infrastructure.
  Clock la `ClockPort` (trong `application/common.py`); `infrastructure/clock.py` chi la implement.
- `presentation`: chuyen HTTP/Pydantic thanh command/query; router khong biet adapter cu the.
  Duoc phep dung domain (enum, error) vi huong vao trong.
- `infrastructure`: implement port cua application; cam import presentation, fastapi, pydantic.
- `bootstrap.py` la composition root duy nhat. Test thay `state` moi cho tung case.

## 3. Chay BE (moi worktree lam 1 lan)

```powershell
cd reference_app
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload --port 8000
```

Kiem tra: `GET /health` -> `{"status": "ok"}`; docs: `http://localhost:8000/docs`.

## 4. Luong chinh da co

- `GET /api/v1/products?search=&page=&size=` -> filter + phan trang qua
  `ProductQueryService` -> `ProductQueryPort` -> `InMemoryProductRepository`.
- `POST /api/v1/movements` (`warehouse_code`, `movement_type`, `lines[]`) ->
  `MovementService.create_draft` kiem tra kho + san pham qua lookup port,
  `StockMovement.create_draft` giu invariant, tra `201` + header `Location`.
- Use case tao phieu KHONG goi stock mutation port: invariant
  "DRAFT khong doi ton kho" nam o dependency graph, khong chi la if/else.

## 5. Quy uoc code

- Domain: `@dataclass(frozen=True)`, invariant trong `__post_init__`,
  tien te dung `Decimal` (`quantity > 0`, `unit_price >= 0`, `price >= 0`).
- Port la `typing.Protocol` nho theo consumer (lookup, paging, repo draft).
  Adapter thay the phai giu contract async.
- Schema Pydantic v2 validate som de OpenAPI tra `422`; domain van tu bao ve
  khi use case duoc goi ngoai HTTP (2 lop bao ve la chu y).
- Loi domain: `NotFoundError` -> `404`, `DomainValidationError` -> `422`
  (xem `error_handlers.py`). Them entity/route moi phai kem test
  unit + acceptance, khong commit code khong chay.

## 6. Git (RULE.md)

Moi nguoi chi code tren worktree + branch cua minh, khong dong vao `main`
truc tiep, code len `main` chi qua PR review. Cau hinh identity theo branch
truoc khi commit. Day du 5 worktree BE:

- `BE` <-> `nhatle08052004n`
- `BE-vule556677`, `BE-lhieu20231`, `BE-xeniellq1`, `BE-thanhson240624`
