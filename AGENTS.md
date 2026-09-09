# BE-Interviewly - Huong dan cho agent

> Day la BE cua prj Interview Coach, dung struct + design pattern cua WMS Lite
> (Clean Architecture + N-layer). KHONG con code nghiep vu WMS nao trong repo.
> Khung hien tai chay duoc (health + auth + OpenAPI + test xanh); them tinh nang
> Interview Coach theo dung vi tri layer duoi day, khong tao lop rong.

## 1. Cay thu muc (khung hien tai)

```text
reference_app/
|-- requirements.txt
|-- docs/openapi.json           tu sync voi app moi lan boot (lifespan)
|-- app/
|   |-- config.py               API_TITLE/VERSION/DESCRIPTION + Settings tu env
|   |-- domain/
|   |   |-- errors.py           DomainError, NotFoundError, DomainValidationError,
|   |   |                       AuthError -> 401, ConflictError -> 409
|   |   `-- identity.py         normalize_email, validate_password/full_name
|   |-- application/
|   |   |-- common.py           PageRequest, PageResult, ClockPort
|   |   |-- container.py        ServiceContainer (clock, settings, engine,
|   |   |                       session_factory, auth_service)
|   |   `-- auth/               commands.py, ports.py, service.py (AuthService)
|   |-- infrastructure/
|   |   |-- clock.py            SystemClock
|   |   |-- database.py         tao engine + check_database
|   |   |-- orm.py              Base + create_session_factory
|   |   |-- security.py         Pbkdf2PasswordHasher (stdlib), JwtTokenService
|   |   `-- persistence/
|   |       |-- models/         17 model SQLAlchemy map 1-1 tu schema.sql
|   |       `-- user_repository.py  SqlAlchemyUserRepository
|   |-- presentation/api/
|   |   |-- dependencies.py     get_container, get_session (moi request 1 session)
|   |   |-- error_handlers.py   404 / 422 / 401 / 409
|   |   |-- routers/auth.py     POST /api/v1/auth/register|login, GET /api/v1/auth/me
|   |   `-- schemas/auth.py     RegisterIn, LoginIn, TokenOut, UserOut (Pydantic v2)
|   |-- bootstrap.py            build_services() - composition root duy nhat
|   `-- main.py                 create_app() + GET /health + lifespan export OpenAPI
`-- tests/
    |-- unit/         invariant + service voi fake port (auth co vi du mau)
    |-- integration/  ORM wiring, create_all tren Postgres
    |-- acceptance/   test API qua TestClient (health, openapi sync, auth)
    `-- architecture/ phan tich import, giu dependency rule
```

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

## 4. Chay BE

### Docker (khuyen dung, co san Postgres)

```powershell
Copy-Item .env.example .env   # sua password neu can, file .env khong commit
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

- API: `http://localhost:8000` (docs: `/docs`, health: `/health`).
- Postgres 16: `localhost:5432` (user/pass/db mac dinh `interviewly`,
  volume `pgdata` giu data). Tat: `docker compose down` (them `-v` de xoa data).
- Bien moi truong: xem `.env.example` (`POSTGRES_*`, `API_PORT`).
  Container api doc `DATABASE_URL` tro ve service `db`, cho doi db healthy
  roi moi start. Bien nay cung la diem cam cho unit persistence sau nay.

### Venv local (moi worktree lam 1 lan)

```powershell
cd reference_app
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload --port 8000
```

Kiem tra: `GET /health` -> `{"status": "ok"}`; docs: `http://localhost:8000/docs`.

## 5. Persistence (nen tang ORM)

- `app/infrastructure/orm.py`: `Base` (SQLAlchemy `DeclarativeBase`, chua co
  model) + `create_session_factory(engine)`.
- `app/infrastructure/database.py`: tao engine + `check_database`.
- `ServiceContainer` giu `engine` + `session_factory`; route can session
  thi `Depends(get_session)` (mo -> yield -> dong, moi request 1 session).
- Them model: tao entity domain truoc, roi map thanh model duoi
  `app/infrastructure/persistence/` (tao thu muc khi co model dau tien),
  Doi cot co san (ALTER) thi create_all khong lo duoc - toi do dung migration.
- ORM tu tao/cap nhat bang: `build_services()` goi `Base.metadata.create_all(engine)` moi lan boot.
  Model song o `app/infrastructure/persistence/models/` (map 1-1 tu `schema.sql`,
  giu nguyen ten bang/cot/enum PG). Them bang = them model + restart api.
- `schema.sql` + ERD giu lam tai lieu goc, khong nap tay nua.
- Pytest can Postgres chay: `docker compose up -d db` truoc khi `pytest -q`.

## 6. Auth (dang nhap / dang ky)

- `POST /api/v1/auth/register` (201): `{full_name, email, password min 8}`.
  Trung email -> `409`. Email chuan hoa lowercase/trim o domain.
- `POST /api/v1/auth/login` (200): `{email, password}` -> `{access_token,
  token_type: bearer}`. Sai thong tin -> `401`.
- `GET /api/v1/auth/me` (200): gui `Authorization: Bearer <token>`.
  Thieu/sai token -> `401`. Response user khong bao gio co password.
- Mat khau hash PBKDF2-SHA256 (stdlib, khong dung bcrypt).
  JWT HS256 qua PyJWT; cau hinh bang env `JWT_SECRET` (toi thieu 32 ky tu
  khi deploy that) va `JWT_EXPIRES_MINUTES` (mac dinh 1440 = 1 ngay).
- Mau test: `tests/unit/test_auth_service.py` (fake port),
  `tests/acceptance/test_auth_api.py` (flow that qua TestClient + Postgres).

## 7. OpenAPI tu sync

- `API_TITLE`/`API_VERSION`/`API_DESCRIPTION` single-source o `app/config.py`,
  `create_app()` doc tu do nen `/openapi.json` khong bao gio lech version.
- Lifespan export `docs/openapi.json` moi lan boot (ca docker lan TestClient
  chay lifespan); test `test_openapi_sync.py` assert file tren dia == spec live.
- Them route moi nho chay pytest de file docs duoc sync roi commit kem.

## 8. Git (RULE.md)

Moi nguoi chi code tren worktree + branch cua minh, khong dong vao `main`
truc tiep, code len `main` chi qua PR review. Cau hinh identity theo branch
truoc khi commit. Day du 5 worktree BE:

- `BE` <-> `nhatle08052004n`
- `BE-vule556677`, `BE-lhieu20231`, `BE-xeniellq1`, `BE-thanhson240624`
