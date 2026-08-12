# Whiskey District Cashout Operations

Internal operations tool that replaces Whiskey District's paper-based end-of-shift cashout process with a digital workflow: AI-extracted document data, structured storage in Postgres, and management-side review and reporting.

Live deployment: <https://cashout-ops.onrender.com>

> **Status:** early build. Authentication (passwordless email sign-in links), error handling, the build/deploy pipeline, cross-cutting plumbing (CSRF, sessions, error contract, OpenAPI shapes), the cashout domain, and the AI document-extraction pipeline are implemented and tested, with a React SPA over the cashier and admin flows. The per-document extraction schemas still hold placeholder fields, and reporting is still to come — tracked in the [Planned scope](#planned-scope) section below.

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
| KV store    | Redis 8 (`redis-py` asyncio client)                     |
| Validation  | Pydantic v2 + `pydantic-settings`                       |
| Auth        | Passwordless email sign-in links, server-side sessions + CSRF double-submit |
| Frontend    | React 19, TypeScript, Vite, TanStack Query, React Router |
| Styling     | Tailwind CSS v4                                         |
| Lint/format | Ruff (Python), ESLint + Prettier (TS/React)             |
| Testing     | pytest + testcontainers (backend), Vitest + Testing Library (frontend) |
| Prod server | Gunicorn + Uvicorn workers                              |
| Doc AI      | Anthropic / OpenAI / Gemini (vision + structured output) |
| Hosting     | Render                                                  |

## What works today

- FastAPI app factory with lifespan-managed async DB engine, session factory, and Redis client
- Passwordless login: submitting an email always returns a challenge (account existence is never revealed); the emailed sign-in link reveals a one-time code, and verifying the code in the initiating tab starts a cookie session — with pluggable `CONSOLE`/`RESEND` email delivery
- Cookie-based session auth backed by SHA-256–hashed session tokens stored in Redis with a TTL
- CSRF protection via double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header on mutating requests)
- Transactional outbox for deferred work (login-link emails, AI extraction): enqueued inside the request transaction, delivered by lifespan-managed dispatcher workers
- Admin user management: list users, create staff accounts, rename them, promote/demote admins, and delete users — plus a single owner role (bootstrapped account; cannot be demoted or deleted) with owner-to-admin ownership transfer
- Centralized domain-error hierarchy with consistent JSON error responses and an `IntegrityError` → `ConflictError` translator
- Pydantic validation errors translated into a stable, UI-friendly contract (`{ type, message, details: [{ field, code, message }] }`)
- camelCase ↔ snake_case casing at the API boundary (`BaseIn` / `BaseOut`)
- Fully-migrated schema: `users`, `outbox_messages`, `cashout_submissions`, `cashout_documents`, `cashout_document_analyses`, and `cashout_data`
- Cashout domain (create/list/delete submission, upload and remove documents with background AI extraction + polling, serve the original document bytes, per-document cashier verification, complete) with a pytest suite over a throwaway Postgres
- AI document pipeline: an LLM classifies each uploaded document and extracts structured data (vision + structured output), decoupled behind provider/storage interfaces — Anthropic, OpenAI, or Gemini, selected by config
- React 19 SPA: auth-guarded routing, light/dark theme with centralized tokens, mobile-first cashier flow (drag-and-drop upload → poll extraction → correct → verify → complete), and admin submissions/data/users views
- Vite build pipeline that emits straight into `backend/static/`, served as a SPA by FastAPI
- Render deploy hooks: `backend/scripts/build.bash`, `pre-deploy.bash`, `start.bash`

## Planned scope

These are designed but not yet implemented in code. Tracked here so the gap between scaffold and intent is explicit.

**Extraction schemas** — the per-document data models (`features/cashout/extraction/schemas.py`) currently hold placeholder fields so the pipeline runs end to end. The real observable fields per document type, deterministic post-extraction validation, and cross-document reconciliation still need to be defined.

**Field-typed correction editors** — the cashier and admin flows are stable, but the verification form still renders every extracted value as a plain text input. Per-document-type editors follow once the extraction schemas are real. Paste-to-upload is also still outstanding (drag-and-drop works).

**Admin flow** — historical views, filtering by date range and server, editing submitted data, discrepancy investigation.

**Reporting** — Excel/CSV/PDF/Google Sheets export, plus Power Query consumption of the Postgres data as the live reporting surface for management.

## Project structure

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/infrastructure`, `app/lib`, `app/security`, `app/errors`, `app/integrations`, and `app/document_ai`. Within a feature, `service.py` owns the workflow and `repository.py` owns all database access (the Redis-backed auth sub-features use a `store.py` instead); services never touch the session or Redis directly. Each module that owns a request-bound resource exposes its FastAPI dependency in a `dependencies.py` beside it (e.g. `infrastructure/db/dependencies.py`'s `get_db`, `features/auth/dependencies.py`'s `get_current_user`).

```
.
├── compose.yaml                       # Postgres 18 + Redis 8 for local dev
├── backend/
│   ├── alembic.ini                    # Alembic config (script_location = migrations/)
│   ├── migrations/                    # Async migrations (env.py reads DATABASE_URL) + versions/
│   ├── pyproject.toml                 # Deps (uv) + ruff + pytest config
│   ├── tests/                         # pytest suite (testcontainers Postgres + Redis)
│   ├── static/                        # Built frontend assets (served by FastAPI)
│   └── app/
│       ├── main.py                    # create_app(); ASGI target app.main:app; SPA fallback
│       ├── lifespan.py                # composition root: enters per-component lifespans, wires app.state
│       ├── core/                      # config/ (one settings group per concern), AI model catalog, storage/email provider enums, cookies, logging, shared schemas
│       ├── infrastructure/            # db/ (Base, registry, lifespan, get_db), redis/ (client, lifespan, get_redis), outbox/ (dispatcher, messages)
│       ├── lib/                       # pure helpers: casing, documents
│       ├── security/                  # CSRF cookies, token crypto, require_csrf, rate_limit/ (Redis fixed window)
│       ├── errors/                    # Domain errors, handlers, translators, OpenAPI shapes
│       ├── integrations/              # ai/ (AIClient + Anthropic/OpenAI/Gemini), email/ (+ get_email_client), storage/ (+ get_document_storage)
│       ├── document_ai/               # DocumentAIClient (generic classify + extract)
│       ├── features/                  # auth (shared/sessions, email_challenges, dependencies: get_current_user/require_admin/require_owner), users, cashout
│       │   └── cashout/extraction/    # CashoutDocumentProcessor, registry, schemas (placeholder fields), get_cashout_document_processor
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
        ├── auth/                      # AuthProvider, guards, passwordless login pages (LoginPage, EmailLoginPage, LoginLinkPage, CodeInput)
        ├── components/                # ui.tsx primitives (token-driven colors only) + dialog / confirm-dialog
        ├── layout/AppLayout.tsx       # mobile-first shell: top bar + bottom nav
        ├── lib/                       # theme provider, formatting helpers, cx
        ├── features/cashout/          # cashier submission flow
        ├── features/admin/            # submissions, data, and users tables
        └── styles/global.css          # Tailwind v4 + centralized light/dark tokens
```

## Local development setup

### Prerequisites

- Python 3.13+
- Node.js (matching `@types/node` 25.x is fine)
- Docker (for the Postgres and Redis containers)

### Manual setup

Backend tooling is [uv](https://docs.astral.sh/uv/), driven through the repo-root `Makefile` (there is no `backend/Makefile` — backend targets call `uv --directory backend` directly).

```bash
# 1. Backend
cp backend/.env.example backend/.env   # then set BOOTSTRAP_OWNER_EMAIL and the selected provider's AI key
make backend-install                   # uv sync (creates .venv, installs incl. dev group)

# 2. Database
make up                                # docker compose up -d (Postgres + Redis)
make backend-migrate                   # uv run alembic upgrade head

# 3. Frontend
make frontend-install                  # npm ci
make frontend-build                    # outputs into backend/static/
```

## Environment variables

All backend variables are loaded from `backend/.env` (see `backend/.env.example`).

Settings are grouped: each variable's prefix names the nested settings model it belongs to, so `STORAGE_LOCAL_DIR` is read as `settings.storage.LOCAL_DIR` and `AUTH_SESSION_TTL_DAYS` as `settings.auth.SESSION_TTL_DAYS` (see [core/config/](backend/app/core/config/)). A few variables stay unprefixed because something outside this app supplies or expects them — the vendor API keys, `DATABASE_URL`, and the `S3_*` pair; those are marked below.

| Variable              | Attribute | Required | Default                                                        | Notes                                                                                                |
| --------------------- | --------- | -------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `APP_ENV`             | `app.ENV` | no       | `prod`                                                         | `prod` or `dev` (validated). Drives `app.DEBUG`, the `Secure` cookie flag, and FastAPI debug mode.   |
| `APP_BASE_URL`        | `app.BASE_URL` | no  | `http://localhost:5173`                                        | Public base URL of the SPA, used to build the emailed sign-in links. Production must set its real origin. |
| `DATABASE_URL`        | `db.URL`  | yes      | —                                                              | Async SQLAlchemy URL (`postgresql+psycopg://…`). Unprefixed: used by both the app and Alembic, and injected under this name by hosting platforms. |
| `REDIS_URL`           | `redis.URL` | yes    | —                                                              | Redis connection URL (`redis://…`). Backs server-side sessions and email challenges; verified with a `PING` at startup.                               |
| `BOOTSTRAP_OWNER_EMAIL` | `bootstrap.OWNER_EMAIL` | no | `owner@test.com`                                    | First sign-in with this email lazily bootstraps the owner account (see [features/auth/email_challenges/service.py](backend/app/features/auth/email_challenges/service.py)). |
| `BOOTSTRAP_OWNER_FULL_NAME` | `bootstrap.OWNER_FULL_NAME` | no | `Owner`                                         | Full name given to the bootstrapped owner account.                                                   |
| `AUTH_SESSION_TTL_DAYS` | `auth.SESSION_TTL_DAYS` | no | `7`                                                     | Session lifetime; also the `session_token` cookie max-age.                                           |
| `AUTH_CHALLENGE_TTL_MINUTES` | `auth.CHALLENGE_TTL_MINUTES` | no | `15`                                           | How long an email challenge (and with it the emailed link and its one-time code) stays valid.         |
| `EMAIL_PROVIDER`      | `email.PROVIDER` | no  | `CONSOLE`                                                      | `CONSOLE` logs emails to stdout (dev default); `RESEND` sends for real and requires `RESEND_API_KEY`. |
| `RESEND_API_KEY`      | `email.RESEND_API_KEY` | see notes | —                                                | Unprefixed (vendor convention). Required only when `EMAIL_PROVIDER=RESEND` (validated at startup).    |
| `EMAIL_FROM`          | `email.FROM` | no      | `Whiskey District <onboarding@resend.dev>`                     | Sender address for all outbound mail.                                                                 |
| `AI_MODEL`            | `ai.MODEL` | no      | `claude-sonnet-5`                                              | Must be one of the models in `AI_PROVIDER_MODELS` ([core/ai_models.py](backend/app/core/ai_models.py)), which lists a default, a cheap, and a premium model per provider; selects the document-AI client built at startup. An unlisted value fails validation at boot. |
| `AI_CLASSIFICATION_MAX_TOKENS` | `ai.CLASSIFICATION_MAX_TOKENS` | no | `512`                                     | Max output tokens for a classification request.                                                      |
| `AI_EXTRACTION_MAX_TOKENS` | `ai.EXTRACTION_MAX_TOKENS` | no  | `2048`                                            | Max output tokens for an extraction request.                                                         |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | `ai.*` | see notes | — | Unprefixed (vendor convention). Only the key for the provider serving `AI_MODEL` is required (the lifespan raises at startup if it's missing). A placeholder lets the app boot; a real key is only needed to hit the extract endpoint. |
| `STORAGE_PROVIDER`    | `storage.PROVIDER` | no | `LOCAL`                                                    | `LOCAL` writes documents under `STORAGE_LOCAL_DIR`; `S3` stores them in `S3_BUCKET`. The selected provider's settings are required; the other provider's are ignored. |
| `STORAGE_LOCAL_DIR`   | `storage.LOCAL_DIR` | see notes | —                                                     | Where uploaded documents are written by the local storage client. Required when `STORAGE_PROVIDER=LOCAL` (the default). |
| `S3_BUCKET`           | `storage.S3_BUCKET` | see notes | —                                                     | Unprefixed, alongside the AWS chain's own variables. Required when `STORAGE_PROVIDER=S3`. Credentials are not configured here — see the note below the table. |
| `S3_REGION`           | `storage.S3_REGION` | see notes | —                                                     | AWS region for the S3 client. Required when `STORAGE_PROVIDER=S3`.                                   |
| `STORAGE_MAX_DOCUMENT_SIZE_MB` | `storage.MAX_DOCUMENT_SIZE_MB` | no | `20`                                      | Largest single document the upload endpoint accepts; a larger body stops being read and is rejected with `DOCUMENT_TOO_LARGE`, whose message carries the configured size. |
| `RATE_LIMIT_AUTH_IP_PER_HOUR` | `rate_limit.AUTH_IP_PER_HOUR` | no | `20`                                          | Per-IP cap on each anonymous auth endpoint (fixed 1-hour window).                                    |
| `RATE_LIMIT_INITIATE_EMAIL_PER_HOUR` | `rate_limit.INITIATE_EMAIL_PER_HOUR` | no | `5`                             | Sign-in emails per address per hour — counted for real and decoy addresses alike.                    |
| `RATE_LIMIT_UPLOADS_PER_USER_PER_HOUR` | `rate_limit.UPLOADS_PER_USER_PER_HOUR` | no | `30`                          | Per-user hourly quota on cashout document uploads (each starts an AI extraction).                    |
| `RATE_LIMIT_EXTRACTS_PER_USER_PER_HOUR` | `rate_limit.EXTRACTS_PER_USER_PER_HOUR` | no | `15`                        | Per-user hourly quota on AI re-extractions.                                                          |
| `OUTBOX_MAX_ATTEMPTS` | `outbox.MAX_ATTEMPTS` | no | `10`                                                     | Delivery attempts before an outbox message dead-letters.                                             |
| `OUTBOX_BATCH_SIZE`   | `outbox.BATCH_SIZE` | no  | `1`                                                        | Messages a dispatcher worker claims per poll.                                                        |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `outbox.POLL_INTERVAL_SECONDS` | no | `1.0`                                     | How often workers poll `outbox_messages` for pending work.                                           |
| `OUTBOX_CLAIM_TTL_SECONDS` | `outbox.CLAIM_TTL_SECONDS` | no  | `30.0`                                            | How long a claim is protected before a crashed worker's row becomes claimable again.                 |
| `OUTBOX_BACKOFF_BASE_SECONDS` | `outbox.BACKOFF_BASE_SECONDS` | no | `5.0`                                         | Retry backoff base — a failed attempt waits `base * 2^(attempt-1)`.                                  |
| `OUTBOX_BACKOFF_CAP_SECONDS` | `outbox.BACKOFF_CAP_SECONDS` | no | `900.0`                                        | Ceiling on that exponential backoff.                                                                 |

The provider is not configured directly: `AI_PROVIDER_MODELS` in [core/ai_models.py](backend/app/core/ai_models.py) lists the models each provider serves, and [core/config/ai.py](backend/app/core/config/ai.py) inverts that map to resolve `settings.ai.PROVIDER` from the configured `AI_MODEL`. Adding a model means adding it to that list.

**AWS credentials are not among these variables.** `S3_BUCKET` and `S3_REGION` say *where* to store documents; boto3 resolves *who* is storing them through its own credential chain, and nothing in `Settings` models or passes a key. That means the credentials must reach the process the way the chain expects:

- **Locally**, configure the chain itself — `aws configure` (writing `~/.aws/credentials`) or `AWS_PROFILE` pointing at an existing profile. Putting `AWS_ACCESS_KEY_ID` in `backend/.env` does **not** work: that file is parsed into `Settings` by pydantic-settings and never exported to the process environment, so boto3 never sees it. A real `export` in your shell does work, since that is a genuine environment variable.
- **In hosted environments**, supply them through the platform's secret or environment-variable system (on Render, the service's environment settings). Deployments on AWS itself can skip static keys entirely and let the chain pick up an instance role, task role, or IRSA.

The frontend currently reads no environment variables.

## Database and migrations

Local Postgres is provisioned by `compose.yaml`:

- Image: `postgres:18`
- User / password: `postgres` / `dev`
- Database: `cashout_ops`
- Port: `5432`
- Named volume: `postgres-data`

The same `compose.yaml` also provisions a local Redis: image `redis:8`, port `6379`, append-only persistence, named volume `redis-data`.

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

**Async all the way down.** The lifespan handler ([app/lifespan.py](backend/app/lifespan.py)) is the composition root: it enters the per-component lifespans (database, Redis, AI, email, storage, and — last, so they stop first on shutdown — the outbox dispatcher workers) and attaches the resulting resources — async engine + `async_sessionmaker`, Redis client, and the external clients — to `app.state`. The per-request `get_db` dependency ([app/infrastructure/db/dependencies.py](backend/app/infrastructure/db/dependencies.py)) yields an `AsyncSession`, commits on success, and rolls back on error — so services never commit.

**AI document pipeline.** Uploaded documents are read directly by a vision model — there is no OCR. The layering keeps the domain off the provider SDK: `CashoutDocumentProcessor` (cashout-specific) → `DocumentAIClient` (generic classify + structured extraction) → an `AIClient` protocol implemented per provider (`AnthropicAIClient`, `OpenAIAIClient`, `GeminiAIClient`) plus a `DocumentStorageClient`. Providers are swappable behind those interfaces, and the tests fake only the provider and storage.

**Settings.** `Settings` ([core/config/](backend/app/core/config/)) is one nested settings group per concern — `app`, `db`, `redis`, `bootstrap`, `auth`, `email`, `ai`, `storage`, `outbox`, `rate_limit` — each a `BaseSettings` reading `.env` under its own `env_prefix`, so code reads `settings.storage.LOCAL_DIR`. Provider-conditional validation lives in the group it belongs to, so an incomplete deployment fails to load its configuration rather than failing on first use. `settings.app.DEBUG` is a computed field derived from `APP_ENV`.

## Authentication and sessions

- Login is passwordless: `POST /api/auth/email-challenges` always returns `202` with a `challengeId` — whether an email was actually sent is never revealed, so the endpoint can't be used for account enumeration. For a real account a magic sign-in link is emailed (via the transactional outbox, once the request commits); the challenge lives in Redis with a TTL (`AUTH_CHALLENGE_TTL_MINUTES`), storing only SHA-256 hashes of the link token and code. Starting a new sign-in invalidates any previous pending challenge for the account.
- Visiting the link (`POST /api/auth/email-challenges/verify-link`) reveals a one-time code and spends the link — it is single-use, so a second click fails; entering the code in the initiating tab (`POST /api/auth/email-challenges/verify-code`) consumes the single-use challenge and creates a session in Redis with an opaque random token, storing **only the SHA-256 hash** of the token as the Redis key, expiring with the session TTL.
- Accounts are created by admins (`POST /api/users`) — there is no self-registration and no password. The `BOOTSTRAP_OWNER_EMAIL` account is bootstrapped lazily on its first sign-in as the single owner (an admin who cannot be demoted or deleted; ownership moves via an explicit transfer).
- The raw token is returned to the client in an HTTP-only `session_token` cookie.
- A `csrf_token` cookie (non-HTTP-only) is set alongside it; mutating requests must echo it back via the `X-CSRF-Token` header (double-submit). CSRF and auth are **not** global — they are applied per-route/router as explicit `require_csrf` ([app/security/dependencies.py](backend/app/security/dependencies.py)) / `get_current_user` / `require_admin` / `require_owner` ([app/features/auth/dependencies.py](backend/app/features/auth/dependencies.py)) dependencies.
- Cookies are `Secure` in production, `SameSite=Lax`, `Path=/`.
- Session TTL is `AUTH_SESSION_TTL_DAYS` (default 7). There is no "remember me".
- Logout clears both cookies and deletes the corresponding Redis session.

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

- `kind` is a broad `SCREAMING_CASE` discriminator that also fixes the HTTP status (`BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION`, `TOO_MANY_REQUESTS`, `INTERNAL`, `SERVICE_UNAVAILABLE` → 400/401/403/404/409/422/429/500/503 via `kind_status_map`).
- `code` is the specific `ErrorCode` — a base code (`INTERNAL`, `BAD_REQUEST`, `VALIDATION_FAILED`, `UNAUTHENTICATED`, `FORBIDDEN`, `ROUTE_NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `SERVICE_UNAVAILABLE`) or a feature code (e.g. `EMAIL_TAKEN`, `USER_NOT_FOUND`, `EMAIL_CHALLENGE_INVALID`). The catalog ([errors/catalog.py](backend/app/errors/catalog.py)) maps each code to its `kind` and default client `message`; each route documents its actual error statuses in OpenAPI via `error_responses(*codes)` ([errors/openapi.py](backend/app/errors/openapi.py)).
- `issues` is present only for validation failures (`VALIDATION`): one entry per field with a `ValidationIssueCode` (`MISSING_FIELD`, `EXTRA_FIELD`, `TOO_SMALL`, …), a `path` array, and a human `message`. Pydantic errors are translated in [errors/translators.py](backend/app/errors/translators.py).
- `TOO_MANY_REQUESTS` (429) responses also carry a `Retry-After` header with the seconds until the rate-limit window resets.
- `IntegrityError` is auto-mapped, first by constraint name (to a feature code) then by Postgres SQLSTATE (unique/FK/restrict → `CONFLICT`, check/not-null → `VALIDATION_FAILED`) in [errors/translators.py](backend/app/errors/translators.py).
- An `AppError`'s internal `message` never reaches the client (it goes to logs/tracebacks only); the response `message` is always the catalog default. Uncaught exceptions are funneled to a generic `INTERNAL` error — no stack traces are leaked.

## API surface

Implemented under the `/api` prefix:

| Method | Path                                          | Auth            | Success | Notes                                                       |
| ------ | --------------------------------------------- | --------------- | ------- | ----------------------------------------------------------- |
| POST   | `/api/auth/email-challenges`                  | none            | 202     | Start a passwordless challenge; always returns a `challengeId` (a real account gets a sign-in link by email). |
| POST   | `/api/auth/email-challenges/verify-link`      | none            | 200     | Verify the emailed link (single-use); returns the one-time code to display. |
| POST   | `/api/auth/email-challenges/verify-code`      | none            | 200     | Complete login in the initiating tab; sets `session_token` + `csrf_token` cookies. |
| POST   | `/api/auth/logout`                            | none            | 204     | Clears both cookies and deletes the Redis session (best-effort). |
| GET    | `/api/users/me`                               | session         | 200     | The current user.                                           |
| GET    | `/api/users`                                  | admin           | 200     | List every user, newest first.                              |
| POST   | `/api/users`                                  | admin + CSRF    | 201     | Create a staff account (no email sent; the user signs in via the login flow). |
| PATCH  | `/api/users/{id}`                             | admin + CSRF    | 200     | Rename a user (any account, the owner's and your own included — a name carries no privileges). |
| POST   | `/api/users/{id}/promote`                     | admin + CSRF    | 200     | Grant a user admin access (idempotent; cannot target the owner). |
| POST   | `/api/users/{id}/demote`                      | admin + CSRF    | 200     | Revoke a user's admin access (cannot demote yourself or the owner). |
| DELETE | `/api/users/{id}`                             | admin + CSRF    | 204     | Delete a user (the owner cannot be deleted). |
| POST   | `/api/users/{id}/transfer-ownership`          | owner + CSRF    | 200     | Transfer ownership to an admin; the caller becomes a plain admin. |
| POST   | `/api/cashout/submissions`                    | session + CSRF  | 201     | Create a cashout submission (any time — not shift-locked).  |
| GET    | `/api/cashout/submissions`                    | session         | 200     | List submissions, newest first — your own as a cashier, everyone's as an admin. |
| GET    | `/api/cashout/submissions/{id}`               | submitter or admin | 200  | Submission detail with documents (analyses embedded) + data. |
| DELETE | `/api/cashout/submissions/{id}`               | submitter + CSRF | 204    | Delete a submission unless reconciled cashout data exists.  |
| POST   | `/api/cashout/submissions/{id}/complete`      | submitter + CSRF | 200    | Reconcile the verified analyses → `COMPLETED`.              |
| POST   | `/api/cashout/submissions/{id}/documents`     | submitter + CSRF | 201    | Upload a document (multipart); returns an `EXTRACTING` analysis — extraction runs in the background. |
| DELETE | `/api/cashout/documents/{id}`                 | submitter + CSRF | 204    | Remove a document and its analysis while the submission is still `PROCESSING`. |
| GET    | `/api/cashout/documents/{id}/content`         | submitter or admin | 200  | Serve the original uploaded bytes inline (image or PDF).    |
| POST   | `/api/cashout/documents/{id}/extract`         | submitter + CSRF | 200    | Restart extraction after a `FAILED` attempt (background, poll again). |
| GET    | `/api/cashout/analyses/{id}`                  | submitter or admin | 200  | Poll the analysis: `EXTRACTING` → `NEEDS_VERIFICATION` \| `FAILED`. |
| POST   | `/api/cashout/analyses/{id}/verify`           | submitter + CSRF | 200    | Confirm an extraction, optionally with corrected values.    |
| GET    | `/api/cashout/data`                           | admin           | 200     | List every reconciled cashout data row, newest first.       |

"Submitter" is the cashier who created the submission — enforced in the cashout service, not by a dependency; it is unrelated to the single **owner** role, which only gates `transfer-ownership`. CSRF is checked on unsafe methods only, so the `GET` rows carry no CSRF requirement even though the routers declare `require_csrf`.

The auth endpoints are rate limited (per client IP on each endpoint, sign-in emails per address, and link verification per challenge), and cashout document upload/extract have per-user hourly quotas — exceeding one returns 429 `RATE_LIMITED` with a `Retry-After` header.

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` while the app is running.

## Deployment

The app is deployed to Render at <https://cashout-ops.onrender.com>.

The three scripts under `backend/scripts/` are the Render deploy hooks:

- `build.bash` — `uv sync` in `backend/`, then `npm ci && npm run build` in `frontend/` (which writes into `backend/static/`).
- `pre-deploy.bash` — `uv run alembic upgrade head` in `backend/`.
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --forwarded-allow-ips='*'`. The start command trusts Render's `X-Forwarded-For` (only the platform proxy can reach the service) so per-IP rate limiting sees real client addresses.

The Render service must have `DATABASE_URL`, `REDIS_URL`, the selected provider's AI key (e.g. `ANTHROPIC_API_KEY`), `BOOTSTRAP_OWNER_EMAIL`, and `APP_BASE_URL` (the deployed origin, used to build the emailed sign-in links) configured (and `APP_ENV=prod`, which is also the default). To actually deliver sign-in link emails set `EMAIL_PROVIDER=RESEND` with `RESEND_API_KEY` and `EMAIL_FROM`; otherwise links are only logged to stdout (`CONSOLE`), so nobody can sign in.

## Conventions

- **API casing.** Inbound and outbound JSON is `camelCase`; Python is `snake_case`. Conversion is handled by `BaseIn`/`BaseOut` via `alias_generator=snake_to_camel`. `BaseIn` is `extra="forbid"`; unknown fields surface as `EXTRA_FIELD` validation issues.
- **Timestamps.** `created_at` is stored UTC and serialized as ISO-8601 with a trailing `Z`.
- **Python typing.** `pyproject.toml` requires Python 3.13+ and configures Pyright in strict mode (`[tool.pyright] typeCheckingMode = "strict"`). Run `make typecheck` (backend Pyright + frontend `tsc`).
- **Lint/format.** Ruff for Python (with import sorting via `extend-select = ["I"]`), Prettier + ESLint for TS/React (the Tailwind plugin sorts classes).
- **Tests.** `make test` runs both suites: Vitest + Testing Library on the frontend, and pytest against a real Postgres and Redis — `TEST_DATABASE_URL` / `TEST_REDIS_URL` if set, otherwise throwaway containers via testcontainers (needs Docker running). The AI provider, object store, and email are faked; the rest of the extraction stack runs for real. See [backend/tests/README.md](backend/tests/README.md) for the unit/integration tiers.

### Known incomplete work

The backend domain and AI pipeline are implemented and tested. What's left:

- **Extraction schemas are placeholders** — `features/cashout/extraction/schemas.py` holds dummy fields per document type. The real observable fields, deterministic post-extraction validation, and cross-document reconciliation (`service._reconcile`) still need to be defined.
- **`LOCAL` document storage is not durable on ephemeral hosts** (such as Render's disk) — uploaded files do not survive a deploy or restart. Durable storage is available: set `STORAGE_PROVIDER=S3` (with `S3_BUCKET` and `S3_REGION`) to store documents in S3 via `S3DocumentStorageClient`; keep `LOCAL` only for development or hosts with a persistent disk. Pointing the client at an S3-compatible store such as MinIO or R2 would need a configurable endpoint, which is no longer modeled.

## License

Proprietary. Copyright © Whiskey District Inc. All rights reserved. See [LICENSE](LICENSE). This repository is published for internal development purposes only; unauthorized copying or distribution is prohibited.
