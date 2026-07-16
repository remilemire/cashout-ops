# Whiskey District Cashout Operations

Internal operations tool that replaces Whiskey District's paper-based end-of-shift cashout process with a digital workflow: AI-extracted document data, structured storage in Postgres, and management-side review and reporting.

Live deployment: <https://cashout-ops.onrender.com>

> **Status:** early build. Authentication, error handling, the build/deploy pipeline, cross-cutting plumbing (CSRF, sessions, error contract, OpenAPI shapes), the shift + cashout domain, and the AI document-extraction pipeline are implemented and tested. The per-document extraction schemas still hold placeholder fields, and the admin/reporting views and frontend are stubbed — tracked in the [Planned scope](#planned-scope) section below.

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

This project replaces that flow with a single pipeline: photograph documents, have an AI model classify each one and extract its structured data, verify the extracted values, and store everything in Postgres as the source of truth. Spreadsheets continue to be the reporting surface for management via Power Query against the database.

The longer-term goal is to grow this into a broader internal operations platform for the restaurant.

## Tech stack

| Layer       | Choice                                                  |
| ----------- | ------------------------------------------------------- |
| Backend     | FastAPI 0.136, Python 3.13+                             |
| ORM         | SQLAlchemy 2.0 (async) + Alembic                        |
| DB driver   | `psycopg` 3 (binary)                                    |
| Database    | PostgreSQL 18                                           |
| Validation  | Pydantic v2 + `pydantic-settings`                       |
| Auth        | Server-side sessions + CSRF double-submit, bcrypt hashes |
| Frontend    | Vue 3, TypeScript, Vite, Pinia, Vue Router              |
| Styling     | Tailwind CSS v4                                         |
| Lint/format | Ruff (Python), ESLint + Prettier (TS/Vue)               |
| Prod server | Gunicorn + Uvicorn workers                              |
| Doc AI      | Anthropic / OpenAI / Gemini (vision + structured output) |
| Hosting     | Render                                                  |

## What works today

- FastAPI app factory with lifespan-managed async DB engine and session factory
- Cookie-based session auth (`/api/auth/login`, `/api/auth/logout`) backed by SHA-256–hashed session tokens stored in Postgres
- CSRF protection via double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header on mutating requests)
- Bcrypt password hashing via `passlib`
- Centralized domain-error hierarchy with consistent JSON error responses and an `IntegrityError` → `ConflictError` translator
- Pydantic validation errors translated into a stable, UI-friendly contract (`{ type, message, details: [{ field, code, message }] }`)
- camelCase ↔ snake_case casing at the API boundary (`BaseIn` / `BaseOut`)
- Fully-migrated schema: `users`, `sessions`, `cashout_submissions`, `cashout_documents`, `cashout_document_analyses`, and `cashout_data`
- Cashout domain (create submission, upload document, AI extract, process, review, complete) with a pytest suite over a throwaway Postgres
- AI document pipeline: an LLM classifies each uploaded document and extracts structured data (vision + structured output), decoupled behind provider/storage interfaces — Anthropic, OpenAI, or Gemini, selected by config
- Vue 3 + Pinia + Vue Router shell with a single placeholder `HomeView`
- Vite build pipeline that emits straight into `backend/static/`, served as a SPA by FastAPI
- Render deploy hooks: `backend/scripts/build.bash`, `pre-deploy.bash`, `start.bash`

## Planned scope

These are designed but not yet implemented in code. Tracked here so the gap between scaffold and intent is explicit.

**Extraction schemas** — the per-document data models (`features/cashout/extraction/schemas.py`) currently hold placeholder fields so the pipeline runs end to end. The real observable fields per document type, deterministic post-extraction validation, and cross-document reconciliation still need to be defined.

**Frontend cashier flow** — create a cashout, upload documents (camera, drag-and-drop, paste, file picker), review extracted fields, submit. The backend endpoints exist; the Vue UI is minimal.

**Admin flow** — historical views, filtering by date range and server, editing submitted data, discrepancy investigation.

**Reporting** — Excel/CSV/PDF/Google Sheets export, plus Power Query consumption of the Postgres data as the live reporting surface for management.

## Project structure

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/lib`, `app/errors`, `app/dependencies`, `app/integrations`, and `app/documents`.

```
.
├── compose.yaml                       # Postgres 18 for local dev
├── setup.bash                         # One-shot local bootstrap
├── backend/
│   ├── alembic.ini                    # Alembic config (script_location = migrations/)
│   ├── migrations/                    # Async migrations (env.py reads DATABASE_URL) + versions/
│   ├── pyproject.toml                 # Deps (uv) + ruff + pytest config
│   ├── Makefile                       # uv-based dev tasks (run/migrate/format/lint/test)
│   ├── tests/                         # pytest suite (testcontainers Postgres)
│   ├── static/                        # Built frontend assets (served by FastAPI)
│   └── app/
│       ├── main.py                    # create_app(); ASGI target app.main:app; SPA fallback
│       ├── lifespan.py                # composition root: DB engine + AI/storage clients on app.state
│       ├── core/                      # config, cookies, db/ (Base, Entity, registry), schemas
│       ├── lib/                       # pure helpers: casing, crypto, documents
│       ├── dependencies/              # FastAPI deps: get_db, auth, csrf, clients
│       ├── errors/                    # Domain errors, handlers, translators, OpenAPI shapes
│       ├── integrations/              # ai/ (AIClient + AnthropicAIClient), storage/
│       ├── documents/                 # DocumentAIClient (generic classify + extract)
│       ├── features/                  # auth, sessions, users, cashout (model/service/router/schemas)
│       │   └── cashout/extraction/    # CashoutDocumentProcessor, registry, schemas (placeholder fields)
│       └── api/__init__.py            # mounts each feature router under /api
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
        ├── api/apiClient.ts           # (minimal — to be implemented)
        └── views/HomeView.vue
```

## Local development setup

### Prerequisites

- Python 3.13+
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

Backend tooling is [uv](https://docs.astral.sh/uv/), driven through the backend `Makefile`.

```bash
# 1. Backend
cd backend
cp .env.example .env                   # then set SECRET_KEY, ADMIN_EMAIL, and the selected provider's AI key
make install                           # uv sync (creates .venv, installs incl. dev group)

# 2. Database
docker compose -f ../compose.yaml up -d
make migrate                           # uv run alembic upgrade head

# 3. Frontend
cd ../frontend
npm ci
npm run build                          # outputs into ../backend/static/
```

## Environment variables

All backend variables are loaded from `backend/.env` (see `backend/.env.example`).

| Variable              | Required | Default                                                        | Notes                                                                                                |
| --------------------- | -------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `ENVIRONMENT`         | no       | `prod`                                                         | `prod` or `dev` (validated). Drives `DEBUG`, the `Secure` cookie flag, and FastAPI debug mode.       |
| `SECRET_KEY`          | yes      | —                                                              | Signs the Starlette session middleware. The app fails to start if unset.                             |
| `DATABASE_URL`        | yes      | —                                                              | Async SQLAlchemy URL (`postgresql+psycopg://…`). Used by both the app and Alembic.                   |
| `AI_PROVIDER`         | no       | `ANTHROPIC`                                                    | `ANTHROPIC`, `OPENAI`, or `GEMINI` — selects the document-AI client built at startup.                |
| `AI_MODEL`            | no       | `claude-opus-4-8`                                              | Model used for classification + extraction; set to one the selected provider serves.                 |
| `AI_MAX_TOKENS`       | no       | `16000`                                                        | Max output tokens per AI request.                                                                    |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | see notes | — | Only the key for the selected `AI_PROVIDER` is required (the lifespan raises at startup if it's missing). A placeholder lets the app boot; a real key is only needed to hit the extract endpoint. |
| `DOCUMENT_STORAGE_DIR`| no       | `storage/documents`                                            | Where uploaded documents are written by the local storage client.                                    |
| `SESSION_TTL_DAYS`    | no       | `7`                                                            | Session lifetime; also the `session_token` cookie max-age.                                           |
| `ADMIN_EMAIL`         | no       | `admin@test.com`                                               | A user registering with this email is promoted to `admin` (see [features/auth/service.py](backend/app/features/auth/service.py)). |

The frontend currently reads no environment variables.

## Database and migrations

Local Postgres is provisioned by `compose.yaml`:

- Image: `postgres:18`
- User / password: `postgres` / `dev`
- Database: `cashout_ops`
- Port: `5432`
- Named volume: `postgres-data`

Alembic reads `DATABASE_URL` from the environment (see [migrations/env.py](backend/migrations/env.py)) and targets `app.core.db.registry.metadata` — a module that imports every ORM model so autogenerate sees the full schema. Add new models to that registry.

```bash
cd backend
make migrate                            # uv run alembic upgrade head
make revision MESSAGE="…"               # autogenerate a new revision
uv run alembic downgrade -1             # revert one
```

## Running the app

### Development

In one terminal — backend (uvicorn with reload, port `8000`):

```bash
cd backend
make run                                # uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal — frontend (Vite dev server, HMR):

```bash
cd frontend
npm run dev
```

Vite's default port is `5173`. The dev server serves the SPA directly; the backend is reachable separately at `http://127.0.0.1:8000`. (There is no proxy configured in `vite.config.mts` yet — wiring API calls during dev will need either a Vite proxy or absolute URLs in the API client.)

### Production-style (built SPA served by FastAPI)

```bash
cd frontend && npm run build            # writes into ../backend/static/
cd ../backend && make run               # FastAPI serves /assets/* and the SPA fallback
```

## Architecture notes

**Single-origin SPA.** Vite builds into `backend/static/`. FastAPI mounts `/assets` as a `StaticFiles` directory and registers a catch-all route that returns `static/index.html` so client-side routing works on hard refresh ([app/main.py](backend/app/main.py)).

**Async all the way down.** The lifespan handler ([app/lifespan.py](backend/app/lifespan.py)) is the composition root: it creates the async engine + `async_sessionmaker` and the document-AI clients, attaching them to `app.state`. The per-request `get_db` dependency ([app/dependencies/db.py](backend/app/dependencies/db.py)) yields an `AsyncSession`, commits on success, and rolls back on error — so services never commit.

**AI document pipeline.** Uploaded documents are read directly by Claude (vision) — there is no OCR. The layering keeps the domain off the provider SDK: `CashoutDocumentProcessor` (cashout-specific) → `DocumentAIClient` (generic classify + structured extraction) → an `AIClient` protocol implemented by `AnthropicAIClient` (Messages API + structured output) and a `DocumentStorageClient`. Providers are swappable behind those interfaces, and the tests fake only the provider and storage. See [CLAUDE.md](CLAUDE.md#document-extraction-pipeline) for the full contract.

**Settings.** `Settings(BaseSettings)` reads `.env`. `DEBUG` is a computed field derived from `ENVIRONMENT`.

## Authentication and sessions

- Register (`POST /api/auth/register`) and login (`POST /api/auth/login`) verify/create the user, then create a `Session` row with an opaque random token (`secrets.token_urlsafe(32)`), storing **only the SHA-256 hash** of the token in the DB.
- The raw token is returned to the client in an HTTP-only `session_token` cookie.
- A `csrf_token` cookie (non-HTTP-only) is set alongside it; mutating requests must echo it back via the `X-CSRF-Token` header (double-submit). CSRF and auth are **not** global — they are applied per-route/router as explicit `require_csrf` / `get_current_user` / `require_admin` dependencies from [app/dependencies/](backend/app/dependencies/).
- Cookies are `Secure` in production, `SameSite=Lax`, `Path=/`.
- Session TTL is `SESSION_TTL_DAYS` (default 7). There is no "remember me".
- Logout clears both cookies and deletes the corresponding session row.

## Error contract

All errors come back as a stable JSON shape so the frontend can render them uniformly:

```json
{
  "error": "Unprocessable Entity",
  "code": "UNPROCESSABLE",
  "message": "There was a problem with the submission.",
  "errors": [
    { "rule": "MISSING_FIELD", "detail": "This field is required.", "path": ["email"] }
  ]
}
```

- `code` is a `SCREAMING_CASE` `ErrorCode` discriminator (`SERVER_ERROR`, `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `ALREADY_EXISTS`, `IN_USE`, `INVALID_STATE`, `UNPROCESSABLE`); `error` is its human name. The catalog ([errors/catalog.py](backend/app/errors/catalog.py)) maps each code to its HTTP status + default message, and the shapes are registered in OpenAPI ([errors/openapi.py](backend/app/errors/openapi.py)).
- `errors` is present only for validation failures (`UNPROCESSABLE`): one entry per field with a `ValidationRule`, a human `detail`, and a `path` array. Pydantic errors are translated in [errors/translators.py](backend/app/errors/translators.py).
- `IntegrityError` is auto-mapped by Postgres SQLSTATE (unique → `ALREADY_EXISTS`, FK → `IN_USE`, check/not-null → `UNPROCESSABLE`) in [errors/handlers.py](backend/app/errors/handlers.py).
- Uncaught exceptions are funneled to a generic `ServerError` — no stack traces are leaked.

## API surface

Implemented under the `/api` prefix:

| Method | Path                                          | Auth            | Notes                                                       |
| ------ | --------------------------------------------- | --------------- | ----------------------------------------------------------- |
| POST   | `/api/auth/register`                          | none            | Creates a user, sets `session_token` + `csrf_token` cookies. |
| POST   | `/api/auth/login`                             | none            | Sets `session_token` + `csrf_token` cookies on success.     |
| POST   | `/api/auth/logout`                            | session + CSRF  | Clears both cookies and deletes the session row.            |
| GET    | `/api/users/me`                               | session         | The current user.                                           |
| POST   | `/api/cashouts`                               | session + CSRF  | Create a cashout submission (any time — not shift-locked).  |
| GET    | `/api/cashouts/{id}`                          | owner or admin  | Submission detail with documents + reconciled data.         |
| POST   | `/api/cashouts/{id}/documents`                | session + CSRF  | Upload a document (multipart file).                         |
| POST   | `/api/cashouts/documents/{id}/extract`        | session + CSRF  | Run AI classification + extraction on a document.           |
| POST   | `/api/cashouts/{id}/process`                  | session + CSRF  | Reconcile extracted data → `UNDER_REVIEW` (or `FAILED`).    |
| PATCH  | `/api/cashouts/data/{id}`                     | admin + CSRF    | Review/correct the extracted data.                          |
| POST   | `/api/cashouts/{id}/complete`                 | admin + CSRF    | Close out a reviewed submission → `COMPLETED`.              |

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` while the app is running.

## Deployment

The app is deployed to Render at <https://cashout-ops.onrender.com>.

The three scripts under `scripts/` (repo root) are the Render deploy hooks:

- `build.bash` — backend `make install` (uv sync), then `npm ci && npm run build` in `frontend/` (which writes into `backend/static/`).
- `pre-deploy.bash` — backend `make migrate` (`alembic upgrade head`).
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT`.

The Render service must have `DATABASE_URL`, `SECRET_KEY`, the selected provider's AI key (e.g. `ANTHROPIC_API_KEY`), and `ADMIN_EMAIL` configured (and `ENVIRONMENT=prod`, which is also the default).

## Conventions

- **API casing.** Inbound and outbound JSON is `camelCase`; Python is `snake_case`. Conversion is handled by `BaseIn`/`BaseOut` via `alias_generator=snake_to_camel`. `BaseIn` is `extra="forbid"`; unknown fields surface as `extra_field` validation errors.
- **Timestamps.** `created_at` is stored UTC and serialized as ISO-8601 with a trailing `Z`.
- **Python typing.** `pyproject.toml` requires Python 3.13+. The repo is configured for Pylance strict mode (see [.vscode/settings.json](.vscode/settings.json)).
- **Lint/format.** Ruff for Python (with import sorting via `extend-select = ["I"]`), Prettier + ESLint for TS/Vue (the Tailwind plugin sorts classes).
- **Tests.** `make test` (pytest) runs against a real Postgres — `TEST_DATABASE_URL` if set, otherwise a throwaway container via testcontainers (needs Docker running). The AI provider and object store are faked; the rest of the extraction stack runs for real.

### Known incomplete work

The backend domain and AI pipeline are implemented and tested. What's left:

- **Extraction schemas are placeholders** — `features/cashout/extraction/schemas.py` holds dummy fields per document type. The real observable fields, deterministic post-extraction validation, and cross-document reconciliation (`service._reconcile`) still need to be defined.
- **Local document storage is not durable on Render** (ephemeral disk) — swap in an object-store implementation of `DocumentStorageClient` before relying on uploaded files surviving a deploy.
- **The frontend is minimal** — the backend endpoints exist, but the Vue UI (upload flow, review, admin views) is a placeholder.

## License

Proprietary. Copyright © Whiskey District Inc. All rights reserved. See [LICENSE](LICENSE). This repository is published for internal development purposes only; unauthorized copying or distribution is prohibited.
