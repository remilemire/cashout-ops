# Whiskey District Cashout Operations

Internal operations tool that replaces Whiskey District's paper-based end-of-shift cashout process with a digital workflow: AI-extracted document data, structured storage in Postgres, and management-side review and reporting.

Live deployment: <https://cashout-ops.onrender.com>

> **Status:** early build. Authentication (invitation-gated registration + email verification), error handling, the build/deploy pipeline, cross-cutting plumbing (CSRF, sessions, error contract, OpenAPI shapes), the cashout domain, and the AI document-extraction pipeline are implemented and tested, with a first-pass React SPA over the cashier and admin flows. The per-document extraction schemas still hold placeholder fields, and reporting plus frontend polish are still to come — tracked in the [Planned scope](#planned-scope) section below.

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
| Frontend    | React 19, TypeScript, Vite, TanStack Query, React Router |
| Styling     | Tailwind CSS v4                                         |
| Lint/format | Ruff (Python), ESLint + Prettier (TS/React)             |
| Prod server | Gunicorn + Uvicorn workers                              |
| Doc AI      | Anthropic / OpenAI / Gemini (vision + structured output) |
| Hosting     | Render                                                  |

## What works today

- FastAPI app factory with lifespan-managed async DB engine and session factory
- Cookie-based session auth (`/api/auth/login`, `/api/auth/logout`) backed by SHA-256–hashed session tokens stored in Postgres
- CSRF protection via double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header on mutating requests)
- Bcrypt password hashing (via the `bcrypt` library directly)
- Invitation-gated registration: an admin invites an email, and only invited emails (plus the bootstrapped `ADMIN_EMAIL`) can register
- Email verification: a short-lived numeric code is emailed on registration; accounts stay gated behind `require_verified_user` until they confirm it (resend supported), with pluggable `CONSOLE`/`RESEND` email delivery
- Admin user management: list users, promote/demote admins, and manage invitations
- Centralized domain-error hierarchy with consistent JSON error responses and an `IntegrityError` → `ConflictError` translator
- Pydantic validation errors translated into a stable, UI-friendly contract (`{ type, message, details: [{ field, code, message }] }`)
- camelCase ↔ snake_case casing at the API boundary (`BaseIn` / `BaseOut`)
- Fully-migrated schema: `users`, `sessions`, `cashout_submissions`, `cashout_documents`, `cashout_document_analyses`, and `cashout_data`
- Cashout domain (create submission, upload document with background AI extraction + polling, per-document cashier verification, complete) with a pytest suite over a throwaway Postgres
- AI document pipeline: an LLM classifies each uploaded document and extracts structured data (vision + structured output), decoupled behind provider/storage interfaces — Anthropic, OpenAI, or Gemini, selected by config
- React 19 SPA (first pass): auth-guarded routing, light/dark theme with centralized tokens, mobile-first cashier flow (upload → poll extraction → correct → verify → complete), and admin submissions/data views
- Vite build pipeline that emits straight into `backend/static/`, served as a SPA by FastAPI
- Render deploy hooks: `backend/scripts/build.bash`, `pre-deploy.bash`, `start.bash`

## Planned scope

These are designed but not yet implemented in code. Tracked here so the gap between scaffold and intent is explicit.

**Extraction schemas** — the per-document data models (`features/cashout/extraction/schemas.py`) currently hold placeholder fields so the pipeline runs end to end. The real observable fields per document type, deterministic post-extraction validation, and cross-document reconciliation still need to be defined.

**Frontend polish** — the React frame (routing, contracts, wiring) is in place; visual design polish, drag-and-drop/paste uploads, and field-typed correction editors (once the extraction schemas are real) are still to come.

**Admin flow** — historical views, filtering by date range and server, editing submitted data, discrepancy investigation.

**Reporting** — Excel/CSV/PDF/Google Sheets export, plus Power Query consumption of the Postgres data as the live reporting surface for management.

## Project structure

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/lib`, `app/errors`, `app/dependencies`, `app/integrations`, and `app/documents`.

```
.
├── compose.yaml                       # Postgres 18 for local dev
├── backend/
│   ├── alembic.ini                    # Alembic config (script_location = migrations/)
│   ├── migrations/                    # Async migrations (env.py reads DATABASE_URL) + versions/
│   ├── pyproject.toml                 # Deps (uv) + ruff + pytest config
│   ├── tests/                         # pytest suite (testcontainers Postgres)
│   ├── static/                        # Built frontend assets (served by FastAPI)
│   └── app/
│       ├── main.py                    # create_app(); ASGI target app.main:app; SPA fallback
│       ├── lifespan.py                # composition root: DB engine + AI/storage clients on app.state
│       ├── core/                      # config, cookies, schemas
│       ├── infrastructure/            # db/ (Base, Entity, registry)
│       ├── lib/                       # pure helpers: casing, documents
│       ├── security/                  # password hashing, session/CSRF cookies, token crypto
│       ├── dependencies/              # FastAPI deps: get_db, auth, csrf, clients
│       ├── errors/                    # Domain errors, handlers, translators, OpenAPI shapes
│       ├── integrations/              # ai/ (AIClient + Anthropic/OpenAI/Gemini), email/, storage/
│       ├── documents/                 # DocumentAIClient (generic classify + extract)
│       ├── features/                  # auth, sessions, users, invitations, email_verification, cashout
│       │   └── cashout/extraction/    # CashoutDocumentProcessor, registry, schemas (placeholder fields)
│       └── api/__init__.py            # mounts each feature router under /api
└── frontend/
    ├── index.html
    ├── vite.config.mts                # outDir → ../backend/static; /api dev proxy
    ├── tsconfig.json                  # @ → src
    ├── eslint.config.mts
    ├── prettier.config.mts
    └── src/
        ├── main.tsx                   # React bootstrap
        ├── App.tsx                    # QueryClient + Theme + Auth providers
        ├── router.tsx                 # auth-guarded routes (cashier + admin)
        ├── api/                       # fetch client (CSRF, error contract) + typed contracts
        ├── auth/                      # AuthProvider, guards, login/register, EmailVerificationGate
        ├── components/ui.tsx          # shared primitives (token-driven colors only)
        ├── layout/AppLayout.tsx       # mobile-first shell: top bar + bottom nav
        ├── lib/                       # theme provider, formatting helpers
        ├── features/cashout/          # cashier submission flow
        ├── features/admin/            # submissions + data tables
        └── styles/global.css          # Tailwind v4 + centralized light/dark tokens
```

## Local development setup

### Prerequisites

- Python 3.13+
- Node.js (matching `@types/node` 25.x is fine)
- Docker (for the Postgres container)



### Manual setup

Backend tooling is [uv](https://docs.astral.sh/uv/), driven through the repo-root `Makefile` (there is no `backend/Makefile` — backend targets call `uv --directory backend` directly).

```bash
# 1. Backend
cp backend/.env.example backend/.env   # then set ADMIN_EMAIL and the selected provider's AI key
make backend-install                   # uv sync (creates .venv, installs incl. dev group)

# 2. Database
make db-up                             # docker compose up -d
make backend-migrate                   # uv run alembic upgrade head

# 3. Frontend
make frontend-install                  # npm ci
make frontend-build                    # outputs into backend/static/
```

## Environment variables

All backend variables are loaded from `backend/.env` (see `backend/.env.example`).

| Variable              | Required | Default                                                        | Notes                                                                                                |
| --------------------- | -------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `ENVIRONMENT`         | no       | `prod`                                                         | `prod` or `dev` (validated). Drives `DEBUG`, the `Secure` cookie flag, and FastAPI debug mode.       |
| `DATABASE_URL`        | yes      | —                                                              | Async SQLAlchemy URL (`postgresql+psycopg://…`). Used by both the app and Alembic.                   |
| `AI_PROVIDER`         | no       | `ANTHROPIC`                                                    | `ANTHROPIC`, `OPENAI`, or `GEMINI` — selects the document-AI client built at startup.                |
| `AI_CLASSIFICATION_MAX_TOKENS` | no | `512`                                                     | Max output tokens for a classification request.                                                      |
| `AI_EXTRACTION_MAX_TOKENS` | no  | `2048`                                                        | Max output tokens for an extraction request.                                                         |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | see notes | — | Only the key for the selected `AI_PROVIDER` is required (the lifespan raises at startup if it's missing). A placeholder lets the app boot; a real key is only needed to hit the extract endpoint. |
| `DOCUMENT_STORAGE_DIR`| no       | `storage/documents`                                            | Where uploaded documents are written by the local storage client.                                    |
| `SESSION_TTL_DAYS`    | no       | `7`                                                            | Session lifetime; also the `session_token` cookie max-age.                                           |
| `INVITATION_TTL_DAYS` | no       | `7`                                                            | How long an invitation stays valid after it's created.                                               |
| `EMAIL_PROVIDER`      | no       | `CONSOLE`                                                      | `CONSOLE` logs emails to stdout (dev default); `RESEND` sends for real and requires `RESEND_API_KEY`. |
| `RESEND_API_KEY`      | see notes | —                                                             | Required only when `EMAIL_PROVIDER=RESEND` (validated at startup).                                    |
| `EMAIL_FROM`          | no       | `Whiskey District <onboarding@resend.dev>`                     | Sender address for all outbound mail.                                                                 |
| `EMAIL_VERIFICATION_CODE_TTL_MINUTES` | no | `15`                                              | How long an emailed verification code stays valid.                                                   |
| `ADMIN_EMAIL`         | no       | `admin@test.com`                                               | A user registering with this email is promoted to `admin` (see [features/auth/service.py](backend/app/features/auth/service.py)). |

The AI model is not env-configurable: each provider's model is fixed in `AI_MODELS` in [core/config.py](backend/app/core/config.py) and resolved for the selected `AI_PROVIDER`.

The frontend currently reads no environment variables.

## Database and migrations

Local Postgres is provisioned by `compose.yaml`:

- Image: `postgres:18`
- User / password: `postgres` / `dev`
- Database: `cashout_ops`
- Port: `5432`
- Named volume: `postgres-data`

Alembic reads `DATABASE_URL` from the environment (see [migrations/env.py](backend/migrations/env.py)) and targets `app.infrastructure.db.registry.metadata` — a module that imports every ORM model so autogenerate sees the full schema. Add new models to that registry.

```bash
make backend-migrate                    # uv run alembic upgrade head
make backend-revision MESSAGE="…"       # autogenerate a new revision
cd backend && uv run alembic downgrade -1  # revert one
```

## Running the app

### Development

In one terminal — backend ([fastapi dev](https://fastapi.tiangolo.com/fastapi-cli/), reload, port `8000`):

```bash
make backend-dev                        # uv run fastapi dev
```

In another terminal — frontend (Vite dev server, HMR):

```bash
make frontend-dev                       # npm run dev
```

Vite's default port is `5173`. `vite.config.mts` proxies `/api` to `http://127.0.0.1:8000`, so the SPA and API are same-origin in dev (cookies and CSRF work unchanged).

### Production-style (built SPA served by FastAPI)

```bash
make frontend-build                     # writes into backend/static/
make backend-dev                        # FastAPI serves /assets/* and the SPA fallback
```

## Architecture notes

**Single-origin SPA.** Vite builds into `backend/static/`. FastAPI mounts `/assets` as a `StaticFiles` directory and registers a catch-all route that returns `static/index.html` so client-side routing works on hard refresh ([app/main.py](backend/app/main.py)).

**Async all the way down.** The lifespan handler ([app/lifespan.py](backend/app/lifespan.py)) is the composition root: it creates the async engine + `async_sessionmaker` and the document-AI clients, attaching them to `app.state`. The per-request `get_db` dependency ([app/dependencies/db.py](backend/app/dependencies/db.py)) yields an `AsyncSession`, commits on success, and rolls back on error — so services never commit.

**AI document pipeline.** Uploaded documents are read directly by a vision model — there is no OCR. The layering keeps the domain off the provider SDK: `CashoutDocumentProcessor` (cashout-specific) → `DocumentAIClient` (generic classify + structured extraction) → an `AIClient` protocol implemented per provider (`AnthropicAIClient`, `OpenAIAIClient`, `GeminiAIClient`) plus a `DocumentStorageClient`. Providers are swappable behind those interfaces, and the tests fake only the provider and storage.

**Settings.** `Settings(BaseSettings)` reads `.env`. `DEBUG` is a computed field derived from `ENVIRONMENT`.

## Authentication and sessions

- Registration is invitation-gated: `POST /api/auth/register` requires a pending invitation for the email (the `ADMIN_EMAIL` account is exempt and is created as an already-verified admin). Register and login (`POST /api/auth/login`) then create a `Session` row with an opaque random token (`secrets.token_urlsafe(32)`), storing **only the SHA-256 hash** of the token in the DB.
- New accounts are emailed a numeric verification code and stay behind the `require_verified_user` gate until they confirm it (`POST /api/email-verification/verify`, resend via `/resend`).
- The raw token is returned to the client in an HTTP-only `session_token` cookie.
- A `csrf_token` cookie (non-HTTP-only) is set alongside it; mutating requests must echo it back via the `X-CSRF-Token` header (double-submit). CSRF and auth are **not** global — they are applied per-route/router as explicit `require_csrf` / `get_current_user` / `require_admin` dependencies from [app/dependencies/](backend/app/dependencies/).
- Cookies are `Secure` in production, `SameSite=Lax`, `Path=/`.
- Session TTL is `SESSION_TTL_DAYS` (default 7). There is no "remember me".
- Logout clears both cookies and deletes the corresponding session row.

## Error contract

All errors come back as a stable JSON shape so the frontend can render them uniformly:

```json
{
  "kind": "VALIDATION",
  "code": "VALIDATION_FAILED",
  "message": "There was a problem with the submission.",
  "issues": [
    { "code": "MISSING_FIELD", "path": ["email"], "message": "This field is required." }
  ]
}
```

- `kind` is a broad `SCREAMING_CASE` discriminator that also fixes the HTTP status (`BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION`, `INTERNAL`, `SERVICE_UNAVAILABLE` → 400/401/403/404/409/422/500/503 via `kind_to_status`).
- `code` is the specific `ErrorCode` — a base code (`INTERNAL`, `BAD_REQUEST`, `VALIDATION_FAILED`, `UNAUTHENTICATED`, `FORBIDDEN`, `ROUTE_NOT_FOUND`, `CONFLICT`, `SERVICE_UNAVAILABLE`) or a feature code (e.g. `EMAIL_TAKEN`, `INVITATION_REQUIRED`, `USER_NOT_FOUND`, `VERIFICATION_CODE_EXPIRED`). The catalog ([errors/catalog.py](backend/app/errors/catalog.py)) maps each code to its `kind` and default client `message`; each route documents its actual error statuses in OpenAPI via `error_responses(*codes)` ([errors/openapi.py](backend/app/errors/openapi.py)).
- `issues` is present only for validation failures (`VALIDATION`): one entry per field with a `ValidationIssueCode` (`MISSING_FIELD`, `EXTRA_FIELD`, `TOO_SMALL`, …), a `path` array, and a human `message`. Pydantic errors are translated in [errors/translators.py](backend/app/errors/translators.py).
- `IntegrityError` is auto-mapped, first by constraint name (to a feature code) then by Postgres SQLSTATE (unique/FK/restrict → `CONFLICT`, check/not-null → `VALIDATION_FAILED`) in [errors/translators.py](backend/app/errors/translators.py).
- An `AppError`'s internal `message` never reaches the client (it goes to logs/tracebacks only); the response `message` is always the catalog default. Uncaught exceptions are funneled to a generic `INTERNAL` error — no stack traces are leaked.

## API surface

Implemented under the `/api` prefix:

| Method | Path                                          | Auth            | Success | Notes                                                       |
| ------ | --------------------------------------------- | --------------- | ------- | ----------------------------------------------------------- |
| POST   | `/api/auth/register`                          | none            | 201     | Requires a pending invitation for the email; creates the user and sets `session_token` + `csrf_token` cookies. |
| POST   | `/api/auth/login`                             | none            | 200     | Sets `session_token` + `csrf_token` cookies on success.     |
| POST   | `/api/auth/logout`                            | session + CSRF  | 204     | Clears both cookies and deletes the session row.            |
| POST   | `/api/email-verification/verify`              | session         | 200     | Confirm the emailed code; marks the account verified.        |
| POST   | `/api/email-verification/resend`              | session         | 204     | Email a fresh code, invalidating the previous one.           |
| GET    | `/api/users/me`                               | session         | 200     | The current user.                                           |
| GET    | `/api/users`                                  | admin           | 200     | List every user, newest first.                              |
| POST   | `/api/users/{id}/promote`                     | admin + CSRF    | 200     | Grant a user admin access (idempotent).                     |
| POST   | `/api/users/{id}/demote`                      | admin + CSRF    | 200     | Revoke a user's admin access (cannot demote yourself).      |
| GET    | `/api/invitations`                            | admin           | 200     | List every invitation, newest first.                        |
| POST   | `/api/invitations`                            | admin + CSRF    | 201     | Invite an email to register.                                |
| DELETE | `/api/invitations/{id}`                        | admin + CSRF    | 204     | Revoke an invitation.                                       |
| POST   | `/api/cashout/submissions`                    | session + CSRF  | 201     | Create a cashout submission (any time — not shift-locked).  |
| DELETE | `/api/cashout/submissions/{id}`               | owner + CSRF    | 204     | Delete a submission unless reconciled cashout data exists.  |
| GET    | `/api/cashout/submissions/{id}`               | owner or admin  | 200     | Submission detail with documents (analyses embedded) + data. |
| POST   | `/api/cashout/submissions/{id}/documents`     | owner + CSRF    | 201     | Upload a document (multipart); returns an `EXTRACTING` analysis — extraction runs in the background. |
| POST   | `/api/cashout/documents/{id}/extract`         | owner + CSRF    | 200     | Restart extraction after a `FAILED` attempt (background, poll again). |
| GET    | `/api/cashout/analyses/{id}`                  | owner or admin  | 200     | Poll the analysis: `EXTRACTING` → `NEEDS_VERIFICATION` \| `FAILED`. |
| POST   | `/api/cashout/analyses/{id}/verify`           | owner + CSRF    | 200     | Confirm an extraction, optionally with corrected values.    |
| POST   | `/api/cashout/submissions/{id}/complete`      | owner + CSRF    | 200     | Reconcile the verified analyses → `COMPLETED`.              |

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` while the app is running.

## Deployment

The app is deployed to Render at <https://cashout-ops.onrender.com>.

The three scripts under `scripts/` (repo root) are the Render deploy hooks:

- `build.bash` — `uv sync` in `backend/`, then `npm ci && npm run build` in `frontend/` (which writes into `backend/static/`).
- `pre-deploy.bash` — `uv run alembic upgrade head` in `backend/`.
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT`.

The Render service must have `DATABASE_URL`, the selected provider's AI key (e.g. `ANTHROPIC_API_KEY`), and `ADMIN_EMAIL` configured (and `ENVIRONMENT=prod`, which is also the default). To actually deliver verification emails set `EMAIL_PROVIDER=RESEND` with `RESEND_API_KEY` and `EMAIL_FROM`; otherwise codes are only logged to stdout (`CONSOLE`), so registered users can't verify.

## Conventions

- **API casing.** Inbound and outbound JSON is `camelCase`; Python is `snake_case`. Conversion is handled by `BaseIn`/`BaseOut` via `alias_generator=snake_to_camel`. `BaseIn` is `extra="forbid"`; unknown fields surface as `EXTRA_FIELD` validation issues.
- **Timestamps.** `created_at` is stored UTC and serialized as ISO-8601 with a trailing `Z`.
- **Python typing.** `pyproject.toml` requires Python 3.13+ and configures Pyright in strict mode (`[tool.pyright] typeCheckingMode = "strict"`). Run `make typecheck` (backend Pyright + frontend `tsc`).
- **Lint/format.** Ruff for Python (with import sorting via `extend-select = ["I"]`), Prettier + ESLint for TS/React (the Tailwind plugin sorts classes).
- **Tests.** `make test` (pytest) runs against a real Postgres — `TEST_DATABASE_URL` if set, otherwise a throwaway container via testcontainers (needs Docker running). The AI provider, object store, and email are faked; the rest of the extraction stack runs for real. See [backend/tests/README.md](backend/tests/README.md) for the unit/integration tiers.

### Known incomplete work

The backend domain and AI pipeline are implemented and tested. What's left:

- **Extraction schemas are placeholders** — `features/cashout/extraction/schemas.py` holds dummy fields per document type. The real observable fields, deterministic post-extraction validation, and cross-document reconciliation (`service._reconcile`) still need to be defined.
- **Local document storage is not durable on Render** (ephemeral disk) — swap in an object-store implementation of `DocumentStorageClient` before relying on uploaded files surviving a deploy.
- **The frontend is a first pass** — the React frame (contracts, guards, flows) works end to end, but visual polish and schema-specific correction editors are pending.

## License

Proprietary. Copyright © Whiskey District Inc. All rights reserved. See [LICENSE](LICENSE). This repository is published for internal development purposes only; unauthorized copying or distribution is prohibited.
