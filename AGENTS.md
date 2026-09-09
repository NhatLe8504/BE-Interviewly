# BE-Interviewly - Huong dan cho agent

> Day la BE cua prj Interview Coach, dung struct + design pattern cua WMS Lite
> (Clean Architecture + N-layer). KHONG con code nghiep vu WMS nao trong repo.
> Khung hien tai chay duoc (health + OpenAPI + test xanh); them tinh nang
> Interview Coach theo dung vi tri layer duoi day, khong tao lop rong.

## 1. Cay thu muc (khung hien tai)

```text
reference_app/
|-- requirements.txt
|-- app/
|   |-- domain/errors.py        DomainError, NotFoundError, DomainValidationError
|   |-- application/
|   |   |-- common.py           PageRequest, PageResult, ClockPort
|   |   `-- container.py        ServiceContainer (hien giu clock)
|   |-- infrastructure/clock.py SystemClock
|   |-- presentation/api/
|   |   |-- dependencies.py     get_container (lay service tu app.state)
|   |   `-- error_handlers.py   NotFoundError -> 404, DomainValidationError -> 422
|   |-- bootstrap.py            build_services() - composition root duy nhat
|   `-- main.py                 create_app() + GET /health
`-- tests/
    |-- acceptance/  test API qua TestClient
    `-- architecture/ phan tich import, giu dependency rule
```

Thu muc `unit/`, `integration/` de trong, dung khi co feature dau tien.

## 2. Dependency rule (bat buoc)

```text
HTTP -> presentation (router + Pydantic) -> application (use case + port) -> domain
infrastructure (adapter) --implements--> application port
bootstrap.py wires moi concrete object
```

- `domain`: chi stdlib. Cam import fastapi, pydantic, application,
  infrastructure, presentation. Entity la `@dataclass(frozen=True)`,
  invariant trong `__post_init__`, tien te dung `Decimal`.
- `application`: duoc import domain. Cam import fastapi, pydantic,
  presentation, infrastructure. Port la `typing.Protocol` nho theo consumer.
  Clock la `ClockPort` (trong `common.py`); infrastructure chi implement.
- `presentation`: chuyen HTTP/Pydantic thanh command/query cua application;
  router khong biet adapter cu the. Schema Pydantic v2 validate som de
  OpenAPI tra `422`; domain van tu bao ve khi use case goi ngoai HTTP.
- `infrastructure`: implement port cua application; cam import presentation,
  fastapi, pydantic.
- `bootstrap.py` la composition root duy nhat. Test tao service/container
  moi cho tung case, khong dung chung state.

## 3. Them 1 feature (vi du: phong phong van)

1. `app/domain/<ten>.py`: entity + enum + invariant thuan Python.
2. `app/application/<ten>/`: `commands.py`, `ports.py` (Protocol),
   `service.py` chi phu thuoc port + domain.
3. `app/infrastructure/...`: adapter implement port (memory truoc, SQL sau).
4. `app/presentation/api/routers/` + `schemas/`: router goi service qua
   dependency, khong import adapter.
5. Wire concrete object trong `bootstrap.py`; them service vao
   `ServiceContainer`.
6. Test: unit (invariant + service voi fake port), acceptance (status, JSON,
   `404`/`422`), khong commit code khong chay.

## 4. Chay BE (moi worktree lam 1 lan)

```powershell
cd reference_app
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload --port 8000
```

Kiem tra: `GET /health` -> `{"status": "ok"}`; docs: `http://localhost:8000/docs`.

## 5. Git (RULE.md)

Moi nguoi chi code tren worktree + branch cua minh, khong dong vao `main`
truc tiep, code len `main` chi qua PR review. Cau hinh identity theo branch
truoc khi commit. Day du 5 worktree BE:

- `BE` <-> `nhatle08052004n`
- `BE-vule556677`, `BE-lhieu20231`, `BE-xeniellq1`, `BE-thanhson240624`
