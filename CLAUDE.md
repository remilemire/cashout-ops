# CLAUDE.md

Guidance for Claude Code sessions working on this repository. Keep it concise and project-specific. Update it when you discover a stable, reusable convention or non-obvious constraint.

## Project

**Whiskey District Cashout Automation** — internal restaurant ops tool. FastAPI backend + Vue 3 SPA, single origin in production (FastAPI serves the built frontend out of `backend/static/`). Deployed to Render at <https://cashout-ops.onrender.com>.

Most domain code is stubbed (`# TODO`). The cross-cutting plumbing (auth, CSRF, error contract, casing, lifespan, migrations skeleton, build/deploy hooks) is the part that's real. New work usually means *implementing* a stubbed model/schema/service, not reshaping the scaffold.

## Layout

```
backend/
  main.py                 uvicorn entrypoint for local dev (port 5001)
  app/__init__.py         create_app(); SPA fallback + StaticFiles mount
  app/core/               settings, lifespan-managed engine, get_db dep
  app/api/                routers; mounted under /api with CSRF dependency
  app/services/           business logic; NEVER commit (see Transactions)
  app/models/             SQLAlchemy ORM; all inherit Entity (id + created_at)
  app/schemas/            Pydantic; inherit BaseIn / BaseOut / EntityOut
  app/utils/              cookies, csrf, passwords, casing, transactions
  app/errors/             domain errors, handlers, OpenAPI shapes, translators
  alembic/                async env.py reads DATABASE_URL from environment
  scripts/                Render deploy hooks (build / pre-deploy / start)
frontend/
  vite.config.mts         outDir → ../backend/static (intentional)
  src/main.ts             Pinia + Vue Router bootstrap
  src/router.ts           single index route today
  src/api/apiClient.ts    empty — implement before adding API calls
compose.yaml              Postgres 18 for local dev
setup.bash                local bootstrap (has known bug — see Gotchas)
```

## Commands

Backend (run from `backend/` with venv active):

```bash
python main.py                          # dev server, http://127.0.0.1:5001, hot reload
alembic upgrade head                    # apply migrations
alembic revision --autogenerate -m "…"  # new migration
alembic downgrade -1                    # revert
ruff check . && ruff format .           # lint + format
pytest                                  # currently no tests exist
```

Frontend (run from `frontend/`):

```bash
npm run dev                             # Vite dev server (no API proxy configured)
npm run build                           # builds into ../backend/static/
npx eslint .
npx prettier --write .
```

Database (from repo root):

```bash
docker compose up -d                    # Postgres 18 on :5432
```

## Environment

Backend loads from `backend/.env` via `pydantic-settings`. Variables:

- `ENVIRONMENT` — `production` (default) or `development`. Drives `settings.DEBUG`, which controls uvicorn reload and the `secure` flag on cookies.
- `SECRET_KEY` — Starlette session middleware signer. **Falls back to a fresh random value per process if unset** — this silently invalidates every session on restart. Always set it in any deployed environment.
- `DATABASE_URL` — async SQLAlchemy URL. Default points at the docker-compose Postgres. Alembic reads this same env var.
- `ADMIN_EMAIL` — when a user is created whose email matches this, `services.users.create` promotes them to `UserRole.ADMIN`.

Frontend reads no env vars currently.

`backend/.env` is checked into the repo (predates the gitignore rule). Don't add real secrets there.

## Architecture rules

### Transactions and where to commit

**Services never commit or flush.** They build/mutate ORM objects and either return them or raise a `DomainError`. The route handler awaits `commit_or_raise(db)` (from `app/utils/transactions.py`) as the final step. `get_db` yields a session per-request; there is no implicit commit on dependency teardown.

If a route mutates the DB and needs the generated PK before responding, call `await flush_or_raise(db)` mid-route.

Service-function shape, by example:

```python
# create-style: pure construction, sync, returns the unsaved object
def create(db, *, payload): ...

# lookup/mutate: async because it needs to fetch first
async def update(db, *, id, payload): ...
```

Use keyword-only arguments after `db` (see existing services in `app/services/`).

### Errors

Always raise the domain errors from `app.errors` rather than `HTTPException`. The handlers in `app/errors/handlers.py` translate them into the canonical envelope:

```json
{ "type": "...", "message": "...", "details": [...] }
```

`IntegrityError` is auto-mapped to `ConflictError` inside `commit_or_raise`/`flush_or_raise` (by Postgres SQLSTATE). Pydantic `ValidationError` / `RequestValidationError` is auto-mapped to `UnprocessableResponse` with per-field codes from `app/errors/translators.py`. Don't hand-craft error JSON.

When adding a new validation `code`, extend `UnprocessableCode` in `app/errors/types.py` and add a message in `app/errors/messages.py`. If the code is context-dependent (uses `ctx`), also add it to `CONTEXTUAL_UNPROCESSABLE_MESSAGES`.

### API conventions

- Everything authenticated lives under `/api`. The `api_router` already attaches `Depends(verify_csrf)`.
- Inbound and outbound JSON is **camelCase**. Python is snake_case. Conversion is automatic via `BaseIn` / `BaseOut` (`alias_generator=snake_to_camel`). Don't manually rename fields.
- `BaseIn` is `extra="forbid"` — unknown fields surface as `extra_field` validation errors. Keep it that way.
- `BaseOut.to_response()` returns dict via `model_dump(by_alias=True, exclude_none=True, mode="json")`. Use it when returning models from handlers.
- `BaseIn.to_update()` returns `model_dump(exclude_unset=True)` — use this in services for partial updates so unset fields don't clobber DB values.
- Timestamps: stored UTC, serialized as ISO-8601 with trailing `Z` (see `EntityOut.serialize_datetime`).
- Register new routers in `app/api/__init__.py` (they inherit CSRF + the `/api` prefix automatically).

### Auth and sessions

- Session token = `secrets.token_urlsafe(32)`. **Only the SHA-256 hash** lives in the `sessions` table; the raw token goes in an HTTP-only `session_token` cookie. Don't change this — comparing tokens means hashing first (`_hash_token` in `services/sessions.py`).
- CSRF: double-submit. `csrf_token` cookie (non-HTTP-only) is set on login; mutating methods under `/api` must echo it in `X-CSRF-Token`. `GET`/`HEAD`/`OPTIONS` skip the check (`utils/csrf.py`).
- Cookies use `Secure=not settings.DEBUG`, `SameSite=Lax`, `Path=/`.
- Session TTL: 12h default, 7d when login payload has `remember=true`.
- Passwords: bcrypt via `passlib` (`utils/passwords.py`). Use `hash_password` / `verify_password`; never store plaintext or pick another scheme.

### Models

All entities inherit `Entity` from `app/models/base.py`, which provides `id`, `created_at`, and an `await Entity.get_active(db, id)` classmethod that raises `NotFoundError` on miss. Use `get_active` instead of `db.get` when "not found" should produce a 404.

When adding a new model: create the file, export from `app/models/__init__.py` (otherwise Alembic autogenerate won't see it), then run `alembic revision --autogenerate -m "…"` and review the diff.

### Authorization

There's no authorization layer yet. When adding admin-only or owner-only endpoints, add an explicit dependency (e.g., a `require_admin` / `require_owner` that uses `sessions.get_user_id`) rather than checking inline.

## Frontend conventions

- Vue 3 `<script setup lang="ts">` SFCs. Pinia for state, Vue Router with `createWebHistory`, Tailwind v4.
- Path alias `@/*` → `frontend/src/*` (configured in both `tsconfig.json` and `vite.config.mts`).
- Vite builds with `outDir: ../backend/static` and `emptyOutDir: true`. **Don't add anything to `backend/static/` by hand — it gets wiped on every build.**
- There is no Vite dev proxy. If you add API calls during dev, either configure one in `vite.config.mts` or use absolute URLs.
- Lint/format: ESLint flat config + Prettier (with `prettier-plugin-tailwindcss` for class sorting). 2-space indent for JS/TS/Vue/HTML/CSS; 4-space for Python (see `.vscode/settings.json`).

## Deployment

Render uses three scripts under `backend/scripts/`:

- `build.bash` — `pip install .` then `npm ci && npm run build` in `frontend/`.
- `pre-deploy.bash` — `alembic upgrade head`.
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT`.

If you change the dependency surface, the install path, or the migration assumptions, update the matching script.

## Known bugs / gotchas

These are real defects in committed code. Fix them if the task touches the relevant area; otherwise leave alone and call them out.

1. **`utils/transactions.py`** — `commit_or_raise` and `flush_or_raise` call `db.commit() / db.flush() / db.rollback()` **without `await`**. The coroutines are silently dropped, so no commits actually happen via these helpers today. Any service-mediated mutation through a real route will appear to succeed but won't persist. Fix when you start writing data-mutating endpoints.
2. **`api/auth.py:20`** — `login` is registered as `@router.get(...)` but reads a JSON body. Should be `@router.post`.
3. **`setup.bash`** — tries to `cp .env.example .env` in `frontend/`, which doesn't exist. Script exits at that step. The frontend has no env vars; remove the block or create a stub `frontend/.env.example` if you ever do need one.
4. **`backend/.env` is tracked.** Don't put real secrets in it. `git rm --cached backend/.env` is safe whenever you want to untrack it.
5. **`backend/static/` artifacts are tracked** despite `static/` being in `.gitignore`. Built JS chunks like `assets/index-*.js` are in the index. New builds produce new hashed filenames, leaving stale ones behind in the working tree.
6. **`frontend/src/vite-end.d.ts`** — typo for `vite-env.d.ts`. The default Vite client types aren't being picked up.
7. **`pytest` in main dependencies** (not `[project.optional-dependencies].dev`). No tests exist yet; if you add tests, move it to `dev` and add a `tests/` dir.

## Stubbed surface

The following all exist as `# TODO` placeholders. Read the existing `User` / `Session` implementations as the template before fleshing any of them out:

- Models: `Shift`, `CashoutSubmission`, `CashoutDocument`, `CashoutData`, `CashoutCorrection`, `OcrResult`, plus column/relationship work on `User` and `Session`.
- Schemas: every file in `app/schemas/` except `base.py`.
- Routers: only `/api/auth/{login,logout}` exists today.
- Frontend: `HomeView.vue` says "Welcome"; `api/apiClient.ts` is empty.
- OCR: Google Cloud Vision is the intended provider; no integration code yet.

The initial Alembic migration (`alembic/versions/0d4aadd52bbb_first_migration.py`) created all eight tables with only `id` and `created_at`. Every real column add lands in a new migration — don't edit the first one.

## Rules for editing

- Don't add `# type: ignore` to silence Pylance — the repo is configured for strict mode in `.vscode/settings.json` and the project relies on it.
- Don't introduce a `requirements.txt`; deps live in `pyproject.toml`.
- Don't switch the DB driver from `psycopg` 3 or break the `postgresql+psycopg://` URL assumption (Alembic's async env relies on it).
- Don't bypass `BaseIn` / `BaseOut` to return raw dicts from API handlers — it skips both the validation and the casing layer.
- Don't catch `Exception` in services to "convert" it — `app/errors/handlers.py` already has a catch-all, and `commit_or_raise` already maps `IntegrityError`.
- Don't add CORS middleware; the app is single-origin by design (SPA served by FastAPI). If you add a dev proxy in `vite.config.mts` instead, that's the right answer.
- Files Claude should read before editing related code:
  - Routes → `app/api/__init__.py`, `app/utils/csrf.py`, `app/errors/__init__.py`
  - Services → `app/services/users.py` (template), `app/utils/transactions.py`
  - Models → `app/models/base.py`, `app/models/__init__.py`
  - Schemas → `app/schemas/base.py`, `app/utils/casing.py`
  - Auth changes → `app/services/sessions.py`, `app/utils/cookies.py`, `app/utils/csrf.py`
  - Migrations → `alembic/env.py`
