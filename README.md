# Whiskey District Cashout Operations

Internal operations tool that replaces Whiskey District's paper-based end-of-shift cashout process with a digital workflow: OCR-extracted document data, structured storage in Postgres, and management-side review and reporting.

Live deployment: <https://cashout-ops.onrender.com>

> **Status:** early scaffold. Authentication, error handling, the build/deploy pipeline, and most cross-cutting plumbing (CSRF, sessions, error contract, OpenAPI shapes) are in place. The domain layer (shifts, cashout submissions, OCR pipeline, admin views, exports) is stubbed and tracked in the [Planned scope](#planned-scope) section below.

---

## Table of contents

- [Problem context](#problem-context)
- [Tech stack](#tech-stack)
- [What works today](#what-works-today)
- [Planned scope](#planned-scope)
- [Project structure](#project-structure)
- [Local development setup](#local-development-setup)
- [Environment variables](#environment-variables)
- [Database and migrations](#database-and-migrations)
- [Running the app](#running-the-app)
- [Architecture notes](#architecture-notes)
- [Authentication and sessions](#authentication-and-sessions)
- [Error contract](#error-contract)
- [API surface](#api-surface)
- [Deployment](#deployment)
- [Conventions](#conventions)
- [License](#license)

---

## Problem context

The current end-of-day cashout process at Whiskey District is heavily manual. Staff reconcile information by hand across paper cashout sheets, debit/credit terminal reports, customer receipts, and TouchBistro shift reports. Management later re-transcribes the same data into spreadsheets. The result is repetitive entry, transcription errors, and discrepancies that aren't noticed until days later.

This project replaces that flow with a single pipeline: photograph documents, run OCR, verify the extracted values, and store everything in Postgres as the source of truth. Spreadsheets continue to be the reporting surface for management via Power Query against the database.

The longer-term goal is to grow this into a broader internal operations platform for the restaurant.

## Tech stack

| Layer       | Choice                                                  |
| ----------- | ------------------------------------------------------- |
| Backend     | FastAPI 0.136, Python 3.12+                             |
| ORM         | SQLAlchemy 2.0 (async) + Alembic                        |
| DB driver   | `psycopg` 3 (binary)                                    |
| Database    | PostgreSQL 18                                           |
| Validation  | Pydantic v2 + `pydantic-settings`                       |
| Auth        | Server-side sessions + CSRF double-submit, bcrypt hashes |
| Frontend    | Vue 3, TypeScript, Vite, Pinia, Vue Router              |
| Styling     | Tailwind CSS v4                                         |
| Lint/format | Ruff (Python), ESLint + Prettier (TS/Vue)               |
| Prod server | Gunicorn + Uvicorn workers                              |
| OCR         | Google Cloud Vision *(planned, not yet integrated)*     |
| Hosting     | Render                                                  |

## What works today

- FastAPI app factory with lifespan-managed async DB engine and session factory
- Cookie-based session auth (`/api/auth/login`, `/api/auth/logout`) backed by SHA-256–hashed session tokens stored in Postgres
- CSRF protection via double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header on mutating requests)
- Bcrypt password hashing via `passlib`
- Centralized domain-error hierarchy with consistent JSON error responses and an `IntegrityError` → `ConflictError` translator
- Pydantic validation errors translated into a stable, UI-friendly contract (`{ type, message, details: [{ field, code, message }] }`)
- camelCase ↔ snake_case casing at the API boundary (`BaseIn` / `BaseOut`)
- Single Alembic migration scaffolding the `users`, `sessions`, `shifts`, `cashout_*`, and `cashout_ocr_results` tables (currently `id` + `created_at` only)
- Vue 3 + Pinia + Vue Router shell with a single placeholder `HomeView`
- Vite build pipeline that emits straight into `backend/static/`, served as a SPA by FastAPI
- Render deploy hooks: `backend/scripts/build.bash`, `pre-deploy.bash`, `start.bash`

## Planned scope

These are designed but not yet implemented in code. Tracked here so the gap between scaffold and intent is explicit.

**Domain models** — `User`, `Session`, `Shift`, `CashoutSubmission`, `CashoutDocument`, `CashoutData`, `CashoutCorrection`, `OcrResult` all exist as `__tablename__`-only stubs; columns and relationships still need to be added and migrated.

**Admin user provisioning** — there is no user-creation endpoint yet. The plan is an admin-only route; the env var `ADMIN_EMAIL` already exists so the first user matching it can be promoted to `admin` on creation (see [services/users.py:31](backend/app/services/users.py#L31)).

**Cashier flow** — start/end shift, upload documents (camera, drag-and-drop, paste, file picker), review extracted fields, submit.

**OCR pipeline** — Google Cloud Vision document text detection, with original images retained alongside extracted data for audit and reprocessing.

**Admin flow** — historical views, filtering by date range and server, editing submitted data, discrepancy investigation.

**Reporting** — Excel/CSV/PDF/Google Sheets export, plus Power Query consumption of the Postgres data as the live reporting surface for management.

## Project structure

```
.
├── compose.yaml                       # Postgres 18 for local dev
├── setup.bash                         # One-shot local bootstrap
├── backend/
│   ├── main.py                        # uvicorn entrypoint (dev)
│   ├── alembic.ini                    # Alembic config (URL injected from env)
│   ├── alembic/
│   │   ├── env.py                     # Async migrations, reads DATABASE_URL
│   │   └── versions/                  # Migration scripts
│   ├── pyproject.toml                 # Deps + ruff config
│   ├── scripts/                       # Render build/pre-deploy/start hooks
│   ├── static/                        # Built frontend assets (served by FastAPI)
│   └── app/
│       ├── __init__.py                # create_app(), SPA fallback, session middleware
│       ├── core/                      # Settings, DB session dep, lifespan
│       ├── api/                       # Routers (currently: auth)
│       ├── services/                  # Business logic (currently: users, sessions)
│       ├── models/                    # SQLAlchemy ORM classes
│       ├── schemas/                   # Pydantic request/response models
│       ├── utils/                     # cookies, csrf, passwords, casing, transactions
│       └── errors/                    # Domain errors, handlers, OpenAPI shapes
└── frontend/
    ├── index.html
    ├── vite.config.mts                # outDir → ../backend/static
    ├── tsconfig.json                  # @ → src
    ├── eslint.config.mts
    ├── prettier.config.mts
    └── src/
        ├── main.ts                    # Pinia + Router bootstrap
        ├── App.vue
        ├── router.ts
        ├── api/apiClient.ts           # (empty — to be implemented)
        └── views/HomeView.vue
```

## Local development setup

### Prerequisites

- Python 3.12+
- Node.js (matching `@types/node` 25.x is fine)
- Docker (for the Postgres container)

### Quick bootstrap

A `setup.bash` script at the repo root automates most of the steps below. It will:

- copy `backend/.env.example` to `backend/.env` if missing
- create `backend/.venv` and install backend deps (incl. `[dev]`)
- run `npm ci` in `frontend/` and build the frontend into `backend/static/`
- start the Postgres container via `docker compose up -d`
- run `alembic upgrade head`

```bash
./setup.bash
```

### Manual setup

```bash
# 1. Backend
cd backend
cp .env.example .env                   # then edit SECRET_KEY and ADMIN_EMAIL
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# 2. Database
docker compose -f ../compose.yaml up -d
alembic upgrade head

# 3. Frontend
cd ../frontend
npm ci
npm run build                          # outputs into ../backend/static/
```

## Environment variables

All backend variables are loaded from `backend/.env` (see `backend/.env.example`).

| Variable        | Required | Default                                                         | Notes                                                                                                |
| --------------- | -------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `ENVIRONMENT`   | no       | `production`                                                    | `production` or `development`. Drives `DEBUG`, secure-cookie flag, and uvicorn auto-reload.          |
| `SECRET_KEY`    | yes\*    | random per-process                                              | Signs the Starlette session middleware. Must be set and stable in any deployed environment.          |
| `DATABASE_URL`  | yes      | `postgresql+psycopg://postgres:dev@localhost:5432/cashout_ops`  | Async SQLAlchemy URL. Used by both the app and Alembic.                                              |
| `ADMIN_EMAIL`   | no       | `admin@test.com`                                                | When a user is created with this email, they are promoted to `admin` (see [services/users.py](backend/app/services/users.py)). |

\* Falls back to a random per-process secret if unset, which invalidates all sessions on restart — fine for ad-hoc local use, not for anything deployed.

The frontend currently reads no environment variables.

## Database and migrations

Local Postgres is provisioned by `compose.yaml`:

- Image: `postgres:18`
- User / password: `postgres` / `dev`
- Database: `cashout_ops`
- Port: `5432`
- Named volume: `postgres-data`

Alembic reads `DATABASE_URL` from the environment (see [alembic/env.py](backend/alembic/env.py)) and targets `app.models.Base.metadata`.

```bash
cd backend
alembic upgrade head                    # apply
alembic revision --autogenerate -m "…"  # create new revision
alembic downgrade -1                    # revert one
```

## Running the app

### Development

In one terminal — backend (uvicorn with reload, port `5001`):

```bash
cd backend
source .venv/bin/activate
python main.py
```

In another terminal — frontend (Vite dev server, HMR):

```bash
cd frontend
npm run dev
```

Vite's default port is `5173`. The dev server serves the SPA directly; the backend is reachable separately at `http://127.0.0.1:5001`. (There is no proxy configured in `vite.config.mts` yet — wiring API calls during dev will need either a Vite proxy or absolute URLs in the API client.)

### Production-style (built SPA served by FastAPI)

```bash
cd frontend && npm run build            # writes into ../backend/static/
cd ../backend && python main.py         # FastAPI serves /assets/* and the SPA fallback
```

## Architecture notes

**Single-origin SPA.** Vite builds into `backend/static/`. FastAPI mounts `/assets` as a `StaticFiles` directory and registers a catch-all route that returns `static/index.html` so client-side routing works on hard refresh ([app/\_\_init\_\_.py:32-36](backend/app/__init__.py#L32-L36)).

**Async all the way down.** Engine and `async_sessionmaker` are created in the lifespan handler and attached to `app.state`; the per-request `get_db` dependency yields an `AsyncSession` from that factory ([core/lifespan.py](backend/app/core/lifespan.py), [core/db.py](backend/app/core/db.py)).

**Settings.** `Settings(BaseSettings)` reads `.env`. `DEBUG` is a computed field derived from `ENVIRONMENT`.

## Authentication and sessions

- Login (`POST /api/auth/login`, see caveat in [Conventions](#conventions)) verifies bcrypt password, creates a `Session` row with an opaque random token (`secrets.token_urlsafe(32)`), and stores **only the SHA-256 hash** of the token in the DB.
- The raw token is returned to the client in an HTTP-only `session_token` cookie.
- A `csrf_token` cookie (non-HTTP-only) is set on login; mutating requests under `/api/*` must echo it back via the `X-CSRF-Token` header. Enforced as a router-level dependency in [api/\_\_init\_\_.py](backend/app/api/__init__.py).
- Cookies are `Secure` in production, `SameSite=Lax`, `Path=/`.
- Session TTL: 12h by default, 7d when `remember=true`.
- Logout clears both cookies and deletes the corresponding session row.

## Error contract

All errors come back as a stable JSON shape so the frontend can render them uniformly:

```json
{
  "type": "unprocessable",
  "message": "There was a problem with the submission.",
  "details": [
    { "field": "email", "code": "missing_field", "message": "This field is required." }
  ]
}
```

- `type` is a string-literal discriminator (`server_error`, `bad_request`, `unauthenticated`, `forbidden`, `not_found`, `conflict`, `unprocessable`) and is registered in OpenAPI for every endpoint ([errors/openapi.py](backend/app/errors/openapi.py)).
- Pydantic validation errors are mapped to a fixed `UnprocessableCode` enum with human-readable, context-aware messages ([errors/translators.py](backend/app/errors/translators.py), [errors/messages.py](backend/app/errors/messages.py)).
- `IntegrityError` is mapped to `ConflictError` by SQLSTATE in [utils/transactions.py](backend/app/utils/transactions.py).
- Uncaught exceptions are funneled to a generic `ServerErrorResponse` — no stack traces are leaked.

## API surface

Currently implemented under the `/api` prefix:

| Method | Path                | Auth         | Notes                                                  |
| ------ | ------------------- | ------------ | ------------------------------------------------------ |
| GET\*  | `/api/auth/login`   | none         | Sets `session_token` and `csrf_token` cookies on success. |
| POST   | `/api/auth/logout`  | session cookie | Clears both cookies and deletes the session row.       |

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` while the app is running.

\* See [Conventions](#conventions) — the login handler is registered as `GET` but reads a JSON body; it should be `POST`.

## Deployment

The app is deployed to Render at <https://cashout-ops.onrender.com>.

The three scripts under `backend/scripts/` are the Render deploy hooks:

- `build.bash` — installs Python deps, then `npm ci && npm run build` in `frontend/` (which writes into `backend/static/`).
- `pre-deploy.bash` — runs `alembic upgrade head`.
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT`.

The Render service must have `DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, and `ENVIRONMENT=production` configured.

## Conventions

- **API casing.** Inbound and outbound JSON is `camelCase`; Python is `snake_case`. Conversion is handled by `BaseIn`/`BaseOut` via `alias_generator=snake_to_camel`. `BaseIn` is `extra="forbid"`; unknown fields surface as `extra_field` validation errors.
- **Timestamps.** `created_at` is stored UTC and serialized as ISO-8601 with a trailing `Z`.
- **Python typing.** `pyproject.toml` requires Python 3.12+. The repo is configured for Pylance strict mode (see [.vscode/settings.json](.vscode/settings.json)).
- **Lint/format.** Ruff for Python (with import sorting via `extend-select = ["I"]`), Prettier + ESLint for TS/Vue (the Tailwind plugin sorts classes).

### Known rough edges

These are real issues in the current code worth fixing before relying on the corresponding paths:

- `POST /api/auth/login` is registered as `@router.get(...)` in [api/auth.py:20](backend/app/api/auth.py#L20) while still reading a JSON body.
- `commit_or_raise` / `flush_or_raise` in [utils/transactions.py](backend/app/utils/transactions.py) call `db.commit()` / `db.flush()` / `db.rollback()` without awaiting them — they return coroutines that are silently dropped.
- `backend/.env` is checked into the repo (predates the `.gitignore` rule); `git rm --cached backend/.env` will untrack it without deleting the local file.
- Built frontend assets under `backend/static/` are tracked in git despite `static/` being in `.gitignore`.
- `pytest` is declared in main dependencies rather than `[project.optional-dependencies].dev`. No tests exist yet.

## License

Proprietary. Copyright © Whiskey District Inc. All rights reserved. See [LICENSE](LICENSE). This repository is published for internal development purposes only; unauthorized copying or distribution is prohibited.
