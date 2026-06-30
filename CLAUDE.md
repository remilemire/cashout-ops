# CLAUDE.md

Guidance for Claude Code sessions working on this repository. Keep it concise and project-specific. Update it when you discover a stable, reusable convention or non-obvious constraint.

## Project

**Whiskey District Cashout Automation** — internal restaurant ops tool. FastAPI backend + Vue 3 SPA, single origin in production (FastAPI serves the built frontend out of `backend/static/`). Deployed to Render at <https://cashout-ops.onrender.com>.

The cross-cutting plumbing (error contract, casing, cookies/CSRF/crypto helpers, lifespan, settings, migrations skeleton, build/deploy hooks) is solid. The **models are all implemented**; **schemas and services are partially implemented** (auth/users/sessions started, the cashout domain still stubbed); the **API routes and frontend are minimal / work-in-progress**. New work usually means *implementing* a stubbed schema/service/route, not reshaping the scaffold.

## Layout

```
backend/
  app/main.py             create_app(); `app = create_app()`; ASGI target is app.main:app; mounts StaticFiles + SPA fallback
  app/__init__.py         empty package marker
  app/lifespan.py         lifespan: creates async engine + sessionmaker on app.state
  app/core/               config (pydantic-settings), passwords (bcrypt), cookies (session/CSRF cookie helpers)
  app/lib/                pure helpers: casing, crypto
  app/api/                routers mounted under /api; dependencies.py (get_db, get_current_user, require_admin, require_csrf)
  app/services/           business logic; build/mutate ORM, may flush, NEVER commit (see Transactions)
  app/models/             SQLAlchemy ORM; all inherit Entity (id + created_at); all models implemented
  app/schemas/            Pydantic; inherit BaseIn / BaseOut / EntityOut
  app/errors/             domain errors, catalog, handlers, translators, schemas, types, OpenAPI shapes
  alembic/                async env.py reads DATABASE_URL from environment
  Makefile                uv-based dev tasks (install/run/format/lint/test/revision/migrate)
frontend/
  vite.config.mts         alias @/* + outDir → ../backend/static (intentional)
  src/main.ts             Pinia + Vue Router bootstrap
  src/router.ts           single index route today
  src/api/apiClient.ts    empty — implement before adding API calls
compose.yaml              Postgres 18 for local dev
scripts/                  Render deploy hooks (build / pre-deploy / start) — at the repo root
setup.bash                local bootstrap (.env, deps, frontend build, migrations)
```

## Commands

Tooling is **uv** (see `uv.lock`) driven through the backend `Makefile`. Run backend targets from `backend/`:

```bash
make install                       # uv sync
make run                           # uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
make migrate                       # uv run alembic upgrade head
make revision MESSAGE="…"          # uv run alembic revision --autogenerate -m "…"
make format                        # uv run ruff format .
make lint                          # uv run ruff check . --fix
make test                          # uv run pytest  (no tests exist yet)
make check                         # format + lint + test
# direct equivalents also work, e.g. `uv run alembic downgrade -1`
```

Frontend (run from `frontend/`):

```bash
npm run dev                        # Vite dev server (no API proxy configured)
npm run build                      # builds into ../backend/static/
npm run lint                       # eslint . --fix
npm run format                     # prettier . --write
npm run test                       # vitest
```

Database (from repo root):

```bash
docker compose up -d               # Postgres 18 on :5432 (user/pw postgres/dev, db cashout_ops)
```

## Environment

Backend loads from `backend/.env` via `pydantic-settings`. `.env` is gitignored; copy `backend/.env.example` to `backend/.env` (setup.bash does this). Variables (see `app/core/config.py`):

- `ENVIRONMENT` — `prod` (default) or `dev`. Validated as a `Literal["prod", "dev"]`. Drives `settings.DEBUG` (`ENVIRONMENT == "dev"`), which controls FastAPI's debug mode and the `Secure` flag on cookies (`Secure = not DEBUG`).
- `SECRET_KEY` — **required, no default**; the app fails to start if unset. Signs the Starlette `SessionMiddleware`.
- `DATABASE_URL` — **required**; async SQLAlchemy URL (`postgresql+psycopg://…`). Alembic reads this same env var.
- `SESSION_TTL_DAYS` — default `7`. Session lifetime.
- `ADMIN_EMAIL` — default `admin@test.com`. `services.auth.register` promotes a user whose email matches to `UserRole.ADMIN`.

Frontend reads no env vars currently.

## Architecture rules

### Transactions and where to commit

**`get_db` owns the transaction.** `app/api/dependencies.py` opens one `AsyncSession` per request, **commits if the handler returns successfully and rolls back if it raises**. Because of this, neither services nor routes need to call `db.commit()` (the WIP auth routes still do, redundantly).

**Services never commit.** They build/mutate ORM objects and either return them or raise a `DomainError`. A service **may** call `await db.flush()` when it needs a generated PK before continuing (see `services/auth.register`, which flushes the new user so the session FK resolves).

Use keyword-only arguments after `db`. Service-function shape, by example:

```python
# create-style: pure construction, sync, returns the unsaved object
def create(db, *, payload, …): ...

# lookup/mutate: async because it must fetch (or flush) first
async def find_by_email(db, *, email): ...
```

### Errors

Always raise the domain errors from `app.errors` (subclasses of `DomainError`) rather than `HTTPException`. The handlers in `app/errors/handlers.py` funnel domain errors — plus translated Pydantic, `IntegrityError`, Starlette HTTP, and uncaught exceptions — through one builder into this body:

```json
{ "error": "...", "code": "...", "message": "...", "errors": [ { "rule": "...", "detail": "...", "path": [...] } ] }
```

The HTTP status comes from `ErrorStatus`; `errors` is present only for validation failures (`UNPROCESSABLE`). `error` is the domain error's human `name`; `code` is the `ErrorCode`. Don't hand-craft error JSON.

- `ErrorCode` and `ValidationRule` are **SCREAMING_CASE** `StrEnum`s in `app/errors/types.py`. The single `CATALOG` in `app/errors/catalog.py` maps each `ErrorCode` → `{status, message, optional details}`; `details` (the per-`ValidationRule` message builders) lives in `VALIDATION_DETAILS`.
- `IntegrityError` is auto-mapped in the handler via `translate_integrity_error` (by Postgres SQLSTATE): unique → `ALREADY_EXISTS`, foreign key → `IN_USE`, check / not-null → `UnprocessableError`, anything else → `ServerError`.
- Pydantic `ValidationError` / `RequestValidationError` → `UNPROCESSABLE`, one `ErrorDetail` per field (`rule` via `translators.PYDANTIC_TO_RULE`, `path` as an array, `detail` from the catalog).
- Catalog `message`/`detail` are **defaults only**: an explicit message passed to a `DomainError`, or an explicit `detail` passed to `ErrorDetail.build(...)`, wins.
- Adding a validation rule: extend `ValidationRule` (types.py) + add a builder in `VALIDATION_DETAILS` (catalog.py) + map the Pydantic type in `PYDANTIC_TO_RULE` (translators.py).
- Adding an error code: extend `ErrorCode` (types.py) + add a `CATALOG` entry (catalog.py) + add a `DomainError` subclass (domain.py) and export it from `errors/__init__.py`.

### API conventions

- Everything lives under `/api`. CSRF and authentication are **not** attached globally on `api_router` — apply them as explicit dependencies (`require_csrf`, `get_current_user` / `require_admin` from `app/api/dependencies.py`) per-route or per-router on what needs them. Register new routers in `app/api/__init__.py` (they inherit the `/api` prefix). `auth_router` and `users_router` are registered.
- Inbound and outbound JSON is **camelCase**; Python is snake_case. Conversion is automatic via `BaseIn` / `BaseOut` (`alias_generator=snake_to_camel`). Don't manually rename fields.
- `BaseIn` is `extra="forbid"` (unknown fields → `EXTRA_FIELD`) and `validate_by_name=True` (can populate by field name). Keep `extra="forbid"`.
- Outbound serialization is the router's job — return a `BaseOut` model and let FastAPI's `response_model` serialize it (`BaseOut` has no `to_response()` helper). The error handlers are the exception: they return `JSONResponse` directly, so they serialize their body by hand with `model_dump(by_alias=True, exclude_none=True, mode="json")` (see `errors/handlers.py:format_error_response`).
- Timestamps: stored UTC, serialized as ISO-8601 with trailing `Z` (see `EntityOut.serialize_datetime`).

### Auth and sessions

- Session token: `crypto.generate_secret_token()` = `secrets.token_urlsafe(32)`. **Only the SHA-256 hash** (`crypto.hash_secret_token`) is stored in `sessions.token_hash`; compare by hashing the incoming token. Don't change this.
- Session lifetime: `SESSION_TTL_DAYS` (default 7). There is no "remember me".
- Passwords: bcrypt via `passlib` in `app/core/passwords.py`. Use `hash_password` / `verify_password`; never store plaintext or pick another scheme.
- Cookies + CSRF live in `app/core/cookies.py`: `Secure = not DEBUG`, `SameSite=Lax`, `Path=/`, `HttpOnly` configurable. The `session_token` cookie is HttpOnly (max-age `SESSION_TTL_DAYS`); the `csrf_token` cookie is readable by JS for the double-submit check (`x-csrf-token` header). Login sets both; logout clears both.
- Dependencies (`app/api/dependencies.py`): `require_csrf` (double-submit; safe methods skip), `get_current_user` (reads the session cookie → `services.auth.authenticate` → `User`), `require_admin` (builds on `get_current_user`).
- Services: `services/sessions.py` (`find_valid_with_user`, `create`, `delete_by_token`), `services/auth.py` (`login`, `register`, `authenticate`, `logout`).

### Models

- All entities inherit `Entity` from `app/models/base.py`, which provides `id`, `created_at`, and `await Entity.get_active(db, id_)` (raises `NotFoundError` on miss — use it instead of `db.get` when a miss should be a 404). `base.py` also exposes `enum_column(enum_cls, name)`, which builds a native Postgres enum column that persists member **values**.
- All models are implemented: `User`, `Session`, `Shift`, `CashoutSubmission`, `CashoutDocument`, `CashoutData`, `OcrResult`. (The former `CashoutCorrection` model was removed.)
- When adding a model: create the file, export it from `app/models/__init__.py` (otherwise Alembic autogenerate won't see it), then `make revision MESSAGE="…"` and review the diff.

### Authorization

Authorization is done with explicit FastAPI dependencies in `app/api/dependencies.py` — `get_current_user` (authentication), `require_admin` (admin-only), `require_csrf` (CSRF). Apply them per-route or per-router via `dependencies=[...]` rather than checking inline. There is no resource/owner-level authorization yet — add it as a dependency when needed.

## Frontend conventions

- Vue 3 `<script setup lang="ts">` SFCs. Pinia for state, Vue Router with `createWebHistory` (single `index` route → `HomeView.vue`), Tailwind v4.
- Path alias `@/*` → `frontend/src/*` (configured in both `tsconfig.json` and `vite.config.mts`).
- Vite builds with `outDir: ../backend/static` and `emptyOutDir: true`. **Don't add anything to `backend/static/` by hand — it gets wiped on every build.**
- There is no Vite dev proxy. If you add API calls during dev, either configure one in `vite.config.mts` or use absolute URLs.
- Lint/format/test via npm scripts (`lint` = eslint --fix, `format` = prettier --write, `test` = vitest). ESLint flat config + Prettier (with `prettier-plugin-tailwindcss` for class sorting).
- Indent: 2-space for JS/TS/Vue/HTML/CSS, 4-space for Python (see `.vscode/settings.json`).

## Deployment

Render uses three scripts at the repo root (`scripts/`):

- `build.bash` — backend `make install` (uv sync), then `npm ci && npm run build` in `frontend/`.
- `pre-deploy.bash` — backend `make migrate` (alembic upgrade head).
- `start.bash` — `uv run gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT`.

If you change the dependency surface, the install path, or the migration assumptions, update the matching script.

## Known bugs / gotchas

These are real defects / mismatches in committed code. Fix them if the task touches the relevant area; otherwise leave alone and call them out.

1. **Migrations are out of sync with the models.** The only migration (`alembic/versions/0d4aadd52bbb_first_migration.py`) creates the eight tables with only `id` + `created_at`, and still includes a `cashout_corrections` table that no longer has a model. The real columns/enums/FKs now on the models are **not yet captured in any migration** — an autogenerate migration is pending. Don't edit the first migration; add a new one.
2. **`start.bash` ASGI target mismatch.** It passes `app:app`, but the ASGI object lives at `app.main:app` (what `make run` uses); `app/__init__.py` doesn't expose `app`. Likely needs `app.main:app`.
3. **`backend/.env.example` sets `ENVIRONMENT=production`**, but the setting only accepts `prod` | `dev` — using `production` will fail validation.
4. **`frontend/src/vite-end.d.ts`** — typo for `vite-env.d.ts`; the default Vite client types aren't being picked up.

## Stubbed / unimplemented surface

- Schemas (`app/schemas/`): `shifts`, `cashout_data`, `cashout_documents`, `cashout_submissions`, `ocr_results` — every `Response`/`Update`/`Create` is `# TODO`. `users.UserOut` is `# TODO` (`UserCreate` is done). `auth.py` is implemented.
- Services: `users`, `sessions`, `auth` are implemented; there's no service for shifts / cashouts / OCR yet.
- API: `api/auth.py` (`login`, `logout`) is implemented; `api/users.py` has a `users_router` whose `get_me` handler is still a `# TODO`. No cashout/shift endpoints yet.
- Frontend: `App.vue` / `HomeView.vue` are minimal; `api/apiClient.ts` is empty.
- OCR: Google Cloud Vision is the intended provider; no integration code yet.
- Tests: `backend/tests/` exists but is empty; `pytest` is in the `dev` dependency group.

## Rules for editing

- The repo runs **Pylance/pyright strict** (`.vscode/settings.json`). Don't add `# type: ignore` to silence real type errors. The only sanctioned ignores are the existing patterns: `reportUnusedFunction` on decorated FastAPI route handlers, and `reportCallIssue` on the `Settings()` instantiation.
- Dependencies live in `pyproject.toml` and are managed by **uv** (`uv.lock`). Don't introduce a `requirements.txt`.
- Don't switch the DB driver from `psycopg` 3 or break the `postgresql+psycopg://` URL assumption (Alembic's async env relies on it).
- Don't bypass `BaseIn` / `BaseOut` to return raw dicts from API handlers — it skips both the validation and the casing layer.
- Don't catch `Exception` in services to "convert" it — `app/errors/handlers.py` already has a catch-all and a dedicated `IntegrityError` handler.
- Don't add CORS middleware; the app is single-origin by design (SPA served by FastAPI). If you need cross-origin during dev, add a proxy in `vite.config.mts`.
- Files to read before editing related code:
  - Routes → `app/api/__init__.py`, `app/api/dependencies.py`, `app/errors/__init__.py`
  - Services → `app/services/users.py` + `app/services/auth.py` (templates), `app/api/dependencies.py` (commit semantics)
  - Models → `app/models/base.py`, `app/models/__init__.py`
  - Schemas → `app/schemas/base.py`, `app/lib/casing.py`
  - Auth changes → `app/services/auth.py`, `app/services/sessions.py`, `app/core/cookies.py`, `app/lib/crypto.py`, `app/core/passwords.py`, `app/api/dependencies.py`
  - Errors → `app/errors/types.py`, `app/errors/catalog.py`, `app/errors/handlers.py`
  - Migrations → `app/models/__init__.py`, `alembic/env.py`
