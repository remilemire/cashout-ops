# Whiskey District Cashout Operations

Internal operations tool that replaces Whiskey District's paper-based end-of-shift cashout process with a digital workflow: AI-extracted document data, structured storage in Postgres, and management-side review and reporting.

Live deployment: <https://whiskeydistrictcashout.com>

> **Status:** Core workflows implemented; actively maintained and extended. Cashiers can upload documents, review AI-extracted values, and submit reconciled cashouts. Administrators can manage submissions and users, review cashout data, and export reports. Remaining workflow improvements and configuration requirements are tracked in [Planned scope](#planned-scope).

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
| Auth        | Passwordless emailed sign-in codes + Google OIDC sign-in (Authlib), server-side sessions + CSRF double-submit |
| Frontend    | React 19, TypeScript, Vite, TanStack Query, React Router |
| Styling     | Tailwind CSS v4                                         |
| Lint/format | Ruff (Python), ESLint + Prettier (TS/React)             |
| Testing     | pytest + testcontainers (backend), Vitest + Testing Library (frontend) |
| Prod server | Gunicorn + Uvicorn workers                              |
| Doc AI      | Anthropic / OpenAI / Gemini (vision + structured output) |
| Cropping    | PP-OCRv4 text detection (onnxruntime, vendored model) finds the documents in an upload — several receipts in a photo, each page of a PDF (pypdfium2) — and crops each out |
| Hosting     | Render                                                  |

## What works today

- FastAPI app factory with lifespan-managed async DB engine, session factory, and Redis client
- Passwordless login: submitting an email always returns a challenge (account existence is never revealed); a one-time code is emailed, and verifying the code starts a cookie session — with pluggable `CONSOLE`/`RESEND` email delivery
- Cookie-based session auth backed by SHA-256–hashed session tokens stored in Redis with a TTL
- CSRF protection via double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header on mutating requests)
- Transactional outbox for deferred work (login-code emails, AI extraction): enqueued inside the request transaction, delivered by lifespan-managed dispatcher workers
- Admin user management: list users, create staff accounts, rename them, promote/demote admins, and delete users — plus a single owner role (bootstrapped account; cannot be demoted or deleted) with owner-to-admin ownership transfer
- Centralized application errors and database-constraint translation, returning `{ kind, code, ctx }`; the frontend owns message wording
- Field validation issues carry Pydantic codes, camelCase paths, and safe constraint context (`issues: [{ code, path, ctx }]`); submitted values and private exception details stay out of responses
- camelCase ↔ snake_case casing at the API boundary (`BaseIn` / `BaseOut`)
- Fully-migrated schema: `users`, `external_identities`, `outbox_messages`, `cashout_submissions`, `cashout_uploads`, `cashout_document_analyses`, and `cashout_data`
- Read-only reporting view `reporting.cashout_data` (the admin cashout data table, for spreadsheet consumers) and the `reporting_reader` role that may read it, both maintained by the migration chain
- Cashout domain (create/list/re-date/delete submission — at most one live cashout per employee per business day, add and remove uploads with background AI extraction + polling, serve an upload's original bytes and the crops its analyses read, per-document cashier verification and unverification, manual entry that skips AI entirely, complete and unsubmit) with a pytest suite over a throwaway Postgres
- Cross-document reconciliation on completion: the server summaries' grand totals and transaction counts must add up to the TouchBistro report's card payments and card orders. Gift certificates' amounts and document count must match its Integrated Gift Cards payment total and transaction count; an absent section means zero activity. Completion fails naming what disagrees
- AI document pipeline: the first extraction uses local text detection to find candidate documents in images and PDF pages. Detected crops are stored beside the original and assigned to separate analyses; an LLM classifies each and extracts structured data. Reruns reuse an existing crop; a sole uncropped analysis retries detection. Detection is heuristic: only the configured number of PDF pages are inspected, and pages without a usable crop are omitted when other pages yield crops. If no crops are found, extraction reads the whole original. Anthropic, OpenAI, or Gemini is selected by config.
- React 19 SPA: auth-guarded routing, light/dark theme with centralized tokens, mobile-first cashier flow (drag-and-drop upload → poll extraction → correct → verify → complete), and admin submissions/data/users views
- Vite build pipeline that emits straight into `backend/static/`, served as a SPA by FastAPI
- Render deploy hooks: `backend/scripts/build.bash`, `pre-deploy.bash`, `start.bash`

## Planned scope

These are designed but not yet finished in code. Tracked here so the gap between what runs today and the intent is explicit.

**Tipout rates** — the per-department rates in `core/config/tipout.py` are placeholders, except the manager's 1%, which is the specified rate. The real rates must replace the others before the app reconciles a real cashout.

**Document-value rules** — schema validation, money normalization, and cross-document reconciliation already run. Additional per-document arithmetic checks need explicit business rules, including treatment of refunds; a blanket ban on negative amounts would reject legitimate data. Money input currently assumes a decimal dot and treats commas as grouping separators, so decimal-comma input is unsupported.

**Field-typed correction editors** — the cashier and admin flows are stable, and the verification form groups and labels fields per document type, but it still renders every value as a plain text input. Per-document-type editors (currency, counts) are the remaining step. Paste-to-upload is also still outstanding (drag-and-drop works).

**Admin flow** — the cashout-data view filters by employee and business day. Administrators can reopen completed submissions, correct their verified document values, and resubmit them. Date-*range* filtering and dedicated discrepancy-investigation tools remain planned.

**Reporting** — the `reporting.cashout_data` view feeds a management Google Sheet, and the admin data table supports CSV export and browser printing. Dedicated Excel/PDF export and Power Query integration remain planned.

## Project structure

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/infrastructure`, `app/lib`, `app/security`, `app/errors`, `app/integrations`, `app/document_ai`, and `app/document_cropping`. Within a feature, `service.py` owns the workflow and `repository.py` owns all database access (the Redis-backed auth sub-features use a `store.py` instead); services never touch the session or Redis directly. Each module that owns a request-bound resource exposes its FastAPI dependency in a `dependencies.py` beside it (e.g. `infrastructure/db/dependencies.py`'s `get_db`, `features/auth/dependencies.py`'s `get_current_user`).

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
│       ├── security/                  # CSRF cookies, token crypto, require_csrf, time_floor, rate_limit/ (Redis fixed window)
│       ├── errors/                    # Domain errors, handlers, translators, OpenAPI shapes
│       ├── integrations/              # ai/ (AIClient + Anthropic/OpenAI/Gemini), email/ (+ get_email_client), oauth/ (Authlib + OAuthIssuer), ocr/ (TextDetector + vendored PP-OCRv4 detector, get_text_detector), storage/ (+ get_document_storage)
│       ├── document_ai/               # DocumentAIClient (generic classify + extract)
│       ├── document_cropping/         # DocumentCropper (find the documents in an image or a PDF's rendered pages, crop each to its detected text)
│       ├── features/                  # auth (sessions/, email_challenges/, oauth/+external_identities/, shared/ (access, accounts), dependencies: get_current_user/require_admin/require_owner), users, cashout
│       │   └── cashout/               # submissions/, uploads/, analyses/, data/ sub-features + shared/ (access policy, upload-intake workflows); thin root router/errors/models/outbox surfaces
│       │       └── extraction/        # CashoutDocumentProcessor (coordinates cropper + document AI: crop stores one crop per document found, process extracts one), registry, per-document schemas with field hints, get_cashout_document_processor
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
        ├── auth/                      # AuthProvider, guards, passwordless login pages (LoginPage, EmailLoginPage, CodeInput)
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

Settings are grouped: each variable's prefix names the nested settings model it belongs to, so `STORAGE_LOCAL_DIR` is read as `settings.storage.LOCAL_DIR` and `AUTH_SESSION_TTL_DAYS` as `settings.auth.SESSION_TTL_DAYS` (see [core/config/](backend/app/core/config/)). A few variables stay unprefixed because something outside this app supplies or expects them — the vendor API keys, `DATABASE_URL`, the `S3_*` pair, and `GCS_BUCKET`; those are marked below.

| Variable              | Attribute | Required | Default                                                        | Notes                                                                                                |
| --------------------- | --------- | -------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `APP_ENV`             | `app.ENV` | no       | `prod`                                                         | `prod` or `dev` (validated). Drives `app.DEBUG`, the `Secure` cookie flag, and FastAPI debug mode.   |
| `APP_BASE_URL`        | `app.BASE_URL` | no  | `http://localhost:5173`                                        | Public base URL of the SPA, used to build the OAuth callback URI. Production must set its real origin. |
| `DATABASE_URL`        | `db.URL`  | yes      | —                                                              | Async SQLAlchemy URL (`postgresql+psycopg://…`). Unprefixed: used by both the app and Alembic, and injected under this name by hosting platforms. |
| `REDIS_URL`           | `redis.URL` | yes    | —                                                              | Redis connection URL (`redis://…`). Backs server-side sessions and email challenges; verified with a `PING` at startup.                               |
| `BOOTSTRAP_OWNER_EMAIL` | `bootstrap.OWNER_EMAIL` | no | `owner@test.com`                                    | First sign-in with this email lazily bootstraps the owner account (see [features/auth/email_challenges/service.py](backend/app/features/auth/email_challenges/service.py)). |
| `BOOTSTRAP_OWNER_FULL_NAME` | `bootstrap.OWNER_FULL_NAME` | no | `Owner`                                         | Full name given to the bootstrapped owner account.                                                   |
| `AUTH_SESSION_TTL_DAYS` | `auth.SESSION_TTL_DAYS` | no | `7`                                                     | Session lifetime; also the `session_token` cookie max-age.                                           |
| `AUTH_CHALLENGE_TTL_MINUTES` | `auth.CHALLENGE_TTL_MINUTES` | no | `15`                                           | Challenge and code lifetime from initiation, including time awaiting delivery.         |
| `AUTH_CHALLENGE_TIME_FLOOR_MS` | `auth.CHALLENGE_TIME_FLOOR_MS` | no | `100`                                      | Timing floor around email-challenge route dependencies. Work above the floor and failures before dependencies run are not hidden. `0` disables. |
| `AUTH_OAUTH_FLOW_TTL_MINUTES` | `auth.OAUTH_FLOW_TTL_MINUTES` | no | `10`                                         | How long a pending OAuth sign-in flow (its Redis state and the `oauth_flow` cookie) stays valid.      |
| `GOOGLE_CLIENT_ID`    | `auth.GOOGLE_CLIENT_ID` | no | —                                                        | Unprefixed (vendor convention). Google sign-in is on exactly when both Google credentials are set — there is no enablement variable, and boot fails on just one of the two. From Google Cloud Console, with authorized redirect URI `<APP_BASE_URL>/api/auth/oauth/google/callback`. |
| `GOOGLE_CLIENT_SECRET` | `auth.GOOGLE_CLIENT_SECRET` | no | —                                                     | Unprefixed (vendor convention). See `GOOGLE_CLIENT_ID` — set together or not at all.                 |
| `EMAIL_PROVIDER`      | `email.PROVIDER` | no  | `console`                                                      | `console` logs emails to stdout (dev default); `resend` sends for real and requires `RESEND_API_KEY`. |
| `RESEND_API_KEY`      | `email.RESEND_API_KEY` | see notes | —                                                | Unprefixed (vendor convention). Required only when `EMAIL_PROVIDER=resend` (validated at startup).    |
| `EMAIL_FROM`          | `email.FROM` | no      | `Whiskey District <onboarding@resend.dev>`                     | Sender address for all outbound mail.                                                                 |
| `AI_MODEL`            | `ai.MODEL` | no      | `claude-sonnet-5`                                              | Must be one of the models in `AI_PROVIDER_MODELS` ([core/ai_models.py](backend/app/core/ai_models.py)), which lists a default, a cheap, and a premium model per provider; selects the document-AI client built at startup. An unlisted value fails validation at boot. |
| `AI_CLASSIFICATION_MAX_TOKENS` | `ai.CLASSIFICATION_MAX_TOKENS` | no | `512`                                     | Max output tokens for a classification request.                                                      |
| `AI_EXTRACTION_MAX_TOKENS` | `ai.EXTRACTION_MAX_TOKENS` | no  | `2048`                                            | Max output tokens for an extraction request.                                                         |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | `ai.*` | see notes | — | Unprefixed (vendor convention). Only the selected provider's key is required; its settings validator rejects a missing key. Provider authentication is checked when the background extraction calls the provider, not when an upload is accepted. |
| `OCR_ENABLED`         | `ocr.ENABLED` | no   | `true`                                                         | Enable text detection and cropping for images and PDF pages. `false` skips model loading and new crops; analyses with existing crops still reuse them. |
| `OCR_DETECTION_MAX_SIDE` | `ocr.DETECTION_MAX_SIDE` | no | `1280`                                            | Maximum image side used for detection; cropping uses the source image resolution. |
| `OCR_CROP_MARGIN`     | `ocr.CROP_MARGIN` | no | `0.03`                                                     | Margin kept around the detected text, as a fraction of the crop's larger side. |
| `OCR_MIN_TEXT_BOXES`  | `ocr.MIN_TEXT_BOXES` | no | `3`                                                     | Minimum text boxes for a candidate crop. Split regions below this threshold are omitted. |
| `OCR_MAX_CROP_AREA_RATIO` | `ocr.MAX_CROP_AREA_RATIO` | no | `0.95`                                          | Skip a single image crop above this area ratio. This limit does not apply to PDF pages or multiple crops from one image. |
| `OCR_DESKEW_ENABLED`  | `ocr.DESKEW_ENABLED` | no | `true`                                                  | Level tilted print (by the dominant orientation of the detected text) before splitting and cropping, so documents lying at an angle still come apart and their crops come out upright. |
| `OCR_SPLIT_ENABLED`   | `ocr.SPLIT_ENABLED` | no | `true`                                                   | Enable heuristic splitting within each image or PDF page. Disabling it does not combine PDF pages. |
| `OCR_SPLIT_GAP`       | `ocr.SPLIT_GAP` | no  | `4.0`                                                       | Minimum gap in median text-line heights considered for a split; background checks are heuristic. |
| `OCR_PDF_RENDER_DPI`  | `ocr.PDF_RENDER_DPI` | no | `200`                                                   | Resolution a PDF page is rendered at before detection and cropping. |
| `OCR_PDF_MAX_PAGES`   | `ocr.PDF_MAX_PAGES` | no | `10`                                                     | Maximum PDF pages inspected for crops. Later pages are omitted if any crops are found; no crops means extraction falls back to the whole original. |
| `STORAGE_PROVIDER`    | `storage.PROVIDER` | no | `local`                                                    | `local` writes documents under `STORAGE_LOCAL_DIR`; `s3` stores them in `S3_BUCKET`; `gcs` stores them in `GCS_BUCKET`. The selected provider's settings are required; the other providers' are ignored. |
| `STORAGE_LOCAL_DIR`   | `storage.LOCAL_DIR` | see notes | —                                                     | Where uploaded documents are written by the local storage client. Required when `STORAGE_PROVIDER=local` (the default). |
| `S3_BUCKET`           | `storage.S3_BUCKET` | see notes | —                                                     | Unprefixed, alongside the AWS chain's own variables. Required when `STORAGE_PROVIDER=s3`. Credentials are not configured here — see the note below the table. |
| `S3_REGION`           | `storage.S3_REGION` | see notes | —                                                     | AWS region for the S3 client. Required when `STORAGE_PROVIDER=s3`.                                   |
| `S3_ENDPOINT_URL`     | `storage.S3_ENDPOINT_URL` | no  | —                                               | Custom endpoint for S3-compatible stores such as MinIO or Cloudflare R2. Optional even under `s3`; unset (or blank) leaves the client on the AWS endpoint for `S3_REGION`. |
| `GCS_BUCKET`          | `storage.GCS_BUCKET` | see notes | —                                                    | Unprefixed, alongside the Application Default Credentials chain's own variables. Required when `STORAGE_PROVIDER=gcs`. Credentials are not configured here — see the note below the table. |
| `STORAGE_MAX_DOCUMENT_SIZE_MB` | `storage.MAX_DOCUMENT_SIZE_MB` | no | `20`                                      | Largest accepted file. The copy from FastAPI's already-parsed upload is limited to this size plus one byte; larger files raise `UPLOAD_TOO_LARGE` with the configured size in `ctx`. This is not a request-body ingestion limit. |
| `RATE_LIMIT_AUTH_IP_PER_HOUR` | `rate_limit.AUTH_IP_PER_HOUR` | no | `20`                                          | Per-IP cap on each anonymous auth endpoint (fixed 1-hour window).                                    |
| `RATE_LIMIT_INITIATE_EMAIL_PER_HOUR` | `rate_limit.INITIATE_EMAIL_PER_HOUR` | no | `5`                             | Sign-in emails per address per hour — counted for real and decoy addresses alike.                    |
| `RATE_LIMIT_UPLOADS_PER_USER_PER_HOUR` | `rate_limit.UPLOADS_PER_USER_PER_HOUR` | no | `30`                          | Per-user hourly quota on cashout uploads, including manual-entry uploads.                             |
| `RATE_LIMIT_EXTRACTS_PER_USER_PER_HOUR` | `rate_limit.EXTRACTS_PER_USER_PER_HOUR` | no | `15`                        | Per-user hourly quota on AI re-extractions.                                                          |
| `OUTBOX_MAX_ATTEMPTS` | `outbox.MAX_ATTEMPTS` | no | `10`                                                     | Delivery attempts before an outbox message dead-letters.                                             |
| `OUTBOX_BATCH_SIZE`   | `outbox.BATCH_SIZE` | no  | `1`                                                        | Messages a dispatcher worker claims per poll.                                                        |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `outbox.POLL_INTERVAL_SECONDS` | no | `1.0`                                     | How often workers poll `outbox_messages` for pending work.                                           |
| `OUTBOX_CLAIM_TTL_SECONDS` | `outbox.CLAIM_TTL_SECONDS` | no  | `30.0`                                            | How long a claim is protected before a crashed worker's row becomes claimable again.                 |
| `OUTBOX_BACKOFF_BASE_SECONDS` | `outbox.BACKOFF_BASE_SECONDS` | no | `5.0`                                         | Retry backoff base — a failed attempt waits `base * 2^(attempt-1)`.                                  |
| `OUTBOX_BACKOFF_CAP_SECONDS` | `outbox.BACKOFF_CAP_SECONDS` | no | `900.0`                                        | Ceiling on that exponential backoff.                                                                 |
| `TIPOUT_BAR_RATE`     | `tipout.BAR_RATE` | no | `0.0500`                                                    | Fraction of **drink** net sales the bar tips out on (`0.05` is 5%). **Placeholder** — see [Planned scope](#planned-scope). Completion snapshots the rate onto the cashout, so a change here only affects cashouts closed afterwards. |
| `TIPOUT_KITCHEN_RATE` | `tipout.KITCHEN_RATE` | no | `0.0300`                                                | Fraction of **food** net sales the kitchen tips out on. **Placeholder**, snapshotted at completion.   |
| `TIPOUT_EXPO_RATE`    | `tipout.EXPO_RATE` | no | `0.0100`                                                   | Fraction of **food** net sales expo tips out on. **Placeholder**, snapshotted at completion.          |
| `TIPOUT_HOST_RATE`    | `tipout.HOST_RATE` | no | `0.0100`                                                   | Fraction of **total** net sales host tips out on. **Placeholder**, snapshotted at completion.         |
| `TIPOUT_MANAGER_RATE` | `tipout.MANAGER_RATE` | no | `0.0100`                                                | Fraction of **total** net sales the manager tips out on — applied to every cashout, not selected by the cashier. The specified rate (1%), snapshotted at completion. |

The provider is not configured directly: `AI_PROVIDER_MODELS` in [core/ai_models.py](backend/app/core/ai_models.py) lists the models each provider serves, and [core/config/ai.py](backend/app/core/config/ai.py) inverts that map to resolve `settings.ai.PROVIDER` from the configured `AI_MODEL`. Adding a model means adding it to that list.

**AWS credentials are not among these variables.** `S3_BUCKET` and `S3_REGION` say *where* to store documents; boto3 resolves *who* is storing them through its own credential chain, and nothing in `Settings` models or passes a key. That means the credentials must reach the process the way the chain expects:

- **Locally**, configure the chain itself — `aws configure` (writing `~/.aws/credentials`) or `AWS_PROFILE` pointing at an existing profile. Putting `AWS_ACCESS_KEY_ID` in `backend/.env` does **not** work: that file is parsed into `Settings` by pydantic-settings and never exported to the process environment, so boto3 never sees it. A real `export` in your shell does work, since that is a genuine environment variable.
- **In hosted environments**, supply them through the platform's secret or environment-variable system (on Render, the service's environment settings). Deployments on AWS itself can skip static keys entirely and let the chain pick up an instance role, task role, or IRSA.

**Google credentials are not among these variables either.** `GCS_BUCKET` says *where* to store documents; google-cloud-storage resolves *who* is storing them through Application Default Credentials (ADC), and nothing in `Settings` models or passes a key. The client resolves those credentials when it is built at startup, so a deployment without them fails to boot rather than at first upload. They must reach the process the way ADC expects:

- **Locally**, `gcloud auth application-default login` (which writes the ADC file under `~/.config/gcloud/`) or an exported `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service-account key file. The same caveat applies: putting `GOOGLE_APPLICATION_CREDENTIALS` in `backend/.env` does **not** work, since pydantic-settings never exports it to the process environment; a real `export` in your shell does.
- **In hosted environments**, supply the service-account key through the platform's secret or environment-variable system and point `GOOGLE_APPLICATION_CREDENTIALS` at it. Deployments on Google-hosted runtimes (Cloud Run, GKE, Compute Engine) can skip the key entirely and let ADC pick up the attached service account.

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

Migrations also own a reporting surface: `reporting.cashout_data`, a read-only view of the admin cashout data table for spreadsheet consumers (the management Google Sheet), and `reporting_reader`, a `NOLOGIN` role that may read it and nothing else. The sheet's login role is created once by hand as a member of that group:

```sql
CREATE ROLE cashout_sheet_reader LOGIN PASSWORD '…' IN ROLE reporting_reader;
```

Postgres refuses to drop a column a view reads, so a migration that rebuilds one of the view's columns drops and recreates the view around the change — [migrations/views.py](backend/migrations/views.py) has the rule.

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

**Resource lifecycles and transactions.** The lifespan handler ([app/lifespan.py](backend/app/lifespan.py)) constructs the database, Redis, and external clients, then starts the outbox workers. Resources live on `app.state`; workers stop before the clients close. The request-scoped `get_db` dependency ([app/infrastructure/db/dependencies.py](backend/app/infrastructure/db/dependencies.py)) commits on success and rolls back on error. Background handlers own their transaction boundaries.

**AI document pipeline.** Two generic components, coordinated by the cashout-specific `CashoutDocumentProcessor` ([features/cashout/extraction/](backend/app/features/cashout/extraction/)), which knows both while neither knows the other. `DocumentCropper` ([document_cropping/](backend/app/document_cropping/)) finds the documents printed in an image — or in each page of a PDF, rendered with pypdfium2 — using a local text-detection model (PP-OCRv4 over onnxruntime, vendored with the app — [integrations/ocr/](backend/app/integrations/ocr/)) and cuts each one out; an empty band on background rather than paper between two blocks of text is what separates two documents, and tilted print is leveled first, by the dominant orientation of the detected text, so documents lying at an angle in a photo still come apart and their crops come out upright. That is detection only, not OCR in the reading sense: no text is recognized. `DocumentAIClient` ([document_ai/](backend/app/document_ai/)) classifies and extracts one document with a vision model. The first extraction of an upload finds its documents and stores a crop of each beside the original: the upload's own analysis takes the first, and the job creates a sibling analysis with its own queued extraction for each further one. Every rerun reads its analysis's crop, the cashier previews it, and the upload's extract endpoint starts it over when the split was wrong. Uploads with no detectable text, and extractions made with `OCR_ENABLED=false`, read the original whole. The layering keeps the domain off the provider SDK: `DocumentAIClient` → an `AIClient` protocol implemented per provider (`AnthropicAIClient`, `OpenAIAIClient`, `GeminiAIClient`) plus a `DocumentStorageClient` and a `TextDetector`. Providers are swappable behind those interfaces, and the tests fake only the provider, storage, and detector.

**Settings.** `Settings` ([core/config/](backend/app/core/config/)) is one nested settings group per concern — `app`, `db`, `redis`, `bootstrap`, `auth`, `email`, `ai`, `ocr`, `storage`, `outbox`, `rate_limit`, `tipout` — each a `BaseSettings` reading `.env` under its own `env_prefix`, so code reads `settings.storage.LOCAL_DIR`. Provider-conditional validation lives in the group it belongs to, so an incomplete deployment fails to load its configuration rather than failing on first use. `settings.app.DEBUG` is a computed field derived from `APP_ENV`.

## Authentication and sessions

- Login is passwordless: accepted `POST /api/auth/email-challenges` requests return `202` with a `challengeId` for both known and unknown addresses. Rate limits, invalid input, and infrastructure failures can return errors. The outbox sends a one-time code for an eligible account after the request commits. Redis stores its SHA-256 hash and the challenge expires after `AUTH_CHALLENGE_TTL_MINUTES`. Initiating a new sign-in deletes the challenge found by the current email pointer, but those Redis operations are not atomic: overlapping requests can leave multiple live challenges. Hashing a six-digit code does not prevent offline enumeration if the hash is exposed; attempt limits constrain online guessing.
- Entering the code (`POST /api/auth/email-challenges/verify-code`) consumes the single-use challenge and creates a session in Redis with an opaque random token, storing **only the SHA-256 hash** of the token as the Redis key, expiring with the session TTL.
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
  "ctx": {},
  "issues": [
    { "code": "missing", "path": ["email"], "ctx": {} }
  ]
}
```

- `kind` is a broad `SCREAMING_CASE` discriminator that also fixes the HTTP status (`BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION`, `TOO_MANY_REQUESTS`, `INTERNAL`, `SERVICE_UNAVAILABLE` → 400/401/403/404/409/422/429/500/503 via `kind_status_map`).
- `code` is the specific `ErrorCode` — a base code (`INTERNAL`, `BAD_REQUEST`, `VALIDATION_FAILED`, `UNAUTHENTICATED`, `FORBIDDEN`, `ROUTE_NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `SERVICE_UNAVAILABLE`) or a feature code (e.g. `EMAIL_TAKEN`, `USER_NOT_FOUND`, `EMAIL_CHALLENGE_INVALID`). The catalog ([errors/catalog.py](backend/app/errors/catalog.py)) maps each code to its `kind`; each route documents its actual error statuses in OpenAPI via `error_responses(*codes)` ([errors/openapi.py](backend/app/errors/openapi.py)).
- `ctx` contains deliberately public JSON values used by the frontend to compose messages; it excludes private diagnostics and submitted values.
- Validation responses may include `issues`: Pydantic codes such as `missing`, `extra_forbidden`, and `greater_than_equal`, camelCase `path` arrays, and safe constraint `ctx` objects. Translation lives in [errors/translators.py](backend/app/errors/translators.py).
- `TOO_MANY_REQUESTS` (429) responses also carry a `Retry-After` header with the seconds until the rate-limit window resets.
- `IntegrityError` is auto-mapped, first by constraint name (to a feature code) then by Postgres SQLSTATE (unique/FK/restrict → `CONFLICT`, check/not-null → `VALIDATION_FAILED`) in [errors/translators.py](backend/app/errors/translators.py).
- An `AppError`'s internal `message` is diagnostic detail and is not serialized into the response. [frontend/src/api/errors.ts](frontend/src/api/errors.ts) owns user-facing wording for both application codes and validation issues. Uncaught exceptions produce a generic `INTERNAL` response.

## API surface

Implemented under the `/api` prefix:

| Method | Path                                          | Auth            | Success | Notes                                                       |
| ------ | --------------------------------------------- | --------------- | ------- | ----------------------------------------------------------- |
| POST   | `/api/auth/email-challenges`                  | none            | 202     | Start a passwordless challenge; always returns a `challengeId` (a real account gets a one-time code by email). |
| POST   | `/api/auth/email-challenges/verify-code`      | none            | 200     | Complete login in the initiating tab; sets `session_token` + `csrf_token` cookies. |
| POST   | `/api/auth/logout`                            | none            | 204     | Clears both cookies and deletes the Redis session (best-effort). |
| GET    | `/api/auth/oauth/{issuer}/start`              | none            | 302     | Begin OAuth sign-in (top-level navigation); sets the `oauth_flow` cookie and redirects to the issuer. |
| GET    | `/api/auth/oauth/{issuer}/callback`           | none            | 302     | Complete OAuth sign-in; sets `session_token` + `csrf_token` cookies and redirects into the SPA (`/login?error={code}` on failure). |
| GET    | `/api/users/me`                               | session         | 200     | The current user.                                           |
| GET    | `/api/users`                                  | admin           | 200     | List every user, newest first.                              |
| POST   | `/api/users`                                  | admin + CSRF    | 201     | Create a staff account (no email sent; the user signs in via the login flow). |
| PATCH  | `/api/users/{id}`                             | admin + CSRF    | 200     | Rename a user (any account, the owner's and your own included — a name carries no privileges). |
| POST   | `/api/users/{id}/promote`                     | admin + CSRF    | 200     | Grant a user admin access (idempotent; cannot target the owner). |
| POST   | `/api/users/{id}/demote`                      | admin + CSRF    | 200     | Revoke a user's admin access (cannot demote yourself or the owner). |
| DELETE | `/api/users/{id}`                             | admin + CSRF    | 204     | Delete a user (the owner cannot be deleted). |
| POST   | `/api/users/{id}/transfer-ownership`          | owner + CSRF    | 200     | Transfer ownership to an admin; the caller becomes a plain admin. |
| POST   | `/api/cashout/submissions`                    | session + CSRF  | 201     | Open a cashout submission (any time — not shift-locked); optional `businessDate` defaults to today, and a second live cashout for the same day conflicts. |
| GET    | `/api/cashout/submissions`                    | session         | 200     | List submissions, newest first — your own as a cashier, everyone's as an admin. |
| GET    | `/api/cashout/submissions/{id}`               | submitter or admin | 200  | Submission detail with uploads (analyses embedded) + data.   |
| DELETE | `/api/cashout/submissions/{id}`               | submitter + CSRF | 204    | Delete a submission unless reconciled cashout data exists.  |
| PATCH  | `/api/cashout/submissions/{id}`               | submitter + CSRF | 200    | Change the business day of a `PROCESSING` cashout (a second live cashout for the new day conflicts); a completed cashout is read-only until unsubmitted. |
| POST   | `/api/cashout/submissions/{id}/complete`      | submitter + CSRF | 200    | Reconcile the verified analyses → `COMPLETED`.              |
| POST   | `/api/cashout/submissions/{id}/unsubmit`      | admin + CSRF     | 200    | Reopen a completed cashout: drops its reconciled data, back to `PROCESSING` (analyses stay verified). |
| POST   | `/api/cashout/submissions/{id}/uploads`       | submitter + CSRF | 201    | Upload a file (multipart); returns its first `EXTRACTING` analysis — extraction runs in the background, one analysis per document found in it. |
| POST   | `/api/cashout/submissions/{id}/uploads/manual` | submitter + CSRF | 201  | Upload a file with its document's manually entered details (multipart); skips AI, so the analysis lands `VERIFIED`. |
| DELETE | `/api/cashout/uploads/{id}`                   | submitter + CSRF | 204    | Remove an upload and its analyses while the submission is still `PROCESSING`. |
| GET    | `/api/cashout/uploads/{id}/content`           | submitter or admin | 200  | Serve the original uploaded bytes inline (image or PDF).    |
| POST   | `/api/cashout/uploads/{id}/extract`           | submitter + CSRF | 200    | Start an upload over: discard its analyses, detect its documents again, re-extract each (background, poll again). |
| GET    | `/api/cashout/analyses/{id}`                  | submitter or admin | 200  | Poll the analysis: `EXTRACTING` → `NEEDS_VERIFICATION` \| `FAILED`. |
| GET    | `/api/cashout/analyses/{id}/cropped`          | submitter or admin | 200  | The crop the analysis read (image bytes, inline); 404 when it read the upload whole. |
| POST   | `/api/cashout/analyses/{id}/extract`          | submitter + CSRF | 200    | Re-run one analysis over the crop it read (background, poll again); an optional `classification` skips the AI classify step. |
| POST   | `/api/cashout/analyses/{id}/manual`           | submitter + CSRF | 200    | Replace an analysis with manually entered details; skips AI, lands `VERIFIED`. |
| POST   | `/api/cashout/analyses/{id}/verify`           | submitter + CSRF | 200    | Confirm an extraction, optionally with corrected values.    |
| POST   | `/api/cashout/analyses/{id}/unverify`         | submitter + CSRF | 200    | Send a verified extraction back to `NEEDS_VERIFICATION` for editing. |
| GET    | `/api/cashout/data`                           | admin           | 200     | List every reconciled cashout data row, newest first.       |

"Submitter" is the cashier who created the submission — enforced in the cashout service ([cashout/shared/access.py](backend/app/features/cashout/shared/access.py)), not by a dependency. Admins (and the owner) have full control over every cashout, so every "submitter" row admits an admin too; it is unrelated to the single **owner** role, which only gates `transfer-ownership`. CSRF is checked on unsafe methods only, so the `GET` rows carry no CSRF requirement even though the routers declare `require_csrf`.

Auth endpoints have per-IP rate limits, and email initiation also has a per-address quota. Cashout upload/extract have per-user quotas. Exceeding these returns 429 `RATE_LIMITED` with `Retry-After`. The separate per-challenge wrong-code budget invalidates the challenge and returns 401 `EMAIL_CHALLENGE_INVALID` when exhausted.

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` while the app is running.

## Deployment

The app is deployed to Render at <https://whiskeydistrictcashout.com>.

The three scripts under `backend/scripts/` are the Render deploy hooks:

- `build.bash` — `uv sync` in `backend/`, then `npm ci && npm run build` in `frontend/` (which writes into `backend/static/`).
- `pre-deploy.bash` — `uv run alembic upgrade head` in `backend/`.
- `start.bash` — `gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --forwarded-allow-ips='*'`. The start command enables wildcard proxy trust; configure rate-limit identity as described below.

### Client IPs and rate limiting on Render

Set `RATE_LIMIT_CLIENT_IP_SOURCE=cloudflare` in the Render service environment before deploying. This makes the shared auth rate limiter use exactly one valid `CF-Connecting-IP` address, normalized so equivalent IPv6 representations share a bucket. Missing, duplicate, or malformed values share an `unknown` bucket; they never fall back to `X-Forwarded-For` or the server-rewritten client address. Health checks are unaffected because this policy is used only by IP rate-limit dependencies.

This setting assumes public requests pass through Cloudflare and that private-network callers are trusted or isolated. Render's [client-IP guidance](https://render.com/articles/host-pocketbase-on-render#making-pocketbase-see-the-real-client-ip) says Cloudflare overwrites `CF-Connecting-IP`, but preserves caller-supplied prefixes in `X-Forwarded-For`. Other services in the same workspace and region may connect through the [private network](https://render.com/docs/private-network) without traversing that edge. A syntactically valid header from such a caller is not proof of origin; restrict that access or treat those services as trusted before enabling this mode.

The default `request_client` mode preserves the ASGI client address for local development and deployments with correctly configured proxy trust. Under wildcard Gunicorn/Uvicorn trust it remains vulnerable to caller-supplied `X-Forwarded-For` prefixes. Render's [Python defaults](https://render.com/docs/environment-variables#python-3) set `FORWARDED_ALLOW_IPS=*`, so removing the command-line wildcard alone does not fix this. The Cloudflare setting changes rate-limit identity only; server access logs and scheme handling still follow the server's proxy configuration.

Before rollout, verify on the actual public path that changing supplied `X-Forwarded-For` and `CF-Connecting-IP` headers cannot change the rate-limit identity. Local tests cannot prove edge sanitization or private-network isolation. Per-email quotas, per-challenge code-attempt limits, and authenticated per-user quotas remain independent protections.

The Render service must have `DATABASE_URL`, `REDIS_URL`, the selected provider's AI key (e.g. `ANTHROPIC_API_KEY`), `BOOTSTRAP_OWNER_EMAIL`, and `APP_BASE_URL` (the deployed origin, used to build the OAuth callback URI) configured (and `APP_ENV=prod`, which is also the default). To actually deliver sign-in code emails set `EMAIL_PROVIDER=resend` with `RESEND_API_KEY` and `EMAIL_FROM`; otherwise codes are only logged to stdout (`console`), so nobody can sign in.

## Conventions

- **API casing.** Inbound and outbound JSON is `camelCase`; Python is `snake_case`. Conversion is handled by `BaseIn`/`BaseOut` via `alias_generator=snake_to_camel`. `BaseIn` is `extra="forbid"`; unknown fields surface as `extra_forbidden` validation issues.
- **Enum values.** Every `StrEnum` member's *value* is `lower_snake_case` (`processing`, `needs_verification`, `s3`) while the member name stays `SCREAMING_SNAKE_CASE` — so the value is what appears in JSON, Postgres enum labels, and configuration, and the name is what Python code spells. The exceptions are values an external format dictates: `DocumentContentType` holds MIME types. The provider selectors read from the environment (`EMAIL_PROVIDER`, `STORAGE_PROVIDER`) accept either case, so a deployment configured before this convention still boots.
- **Timestamps.** `created_at` is stored UTC and serialized as ISO-8601 with a trailing `Z`.
- **Monetary rounding.** Source-document amounts and configured tipout rates are preserved as reported. Calculated tipouts round each department separately upward to cent precision in the house's favour (the manager, who tips out on every cashout, included; amounts already on a cent stay unchanged), and the final signed settlement uses the same rule: employee obligations round up while house obligations round toward zero. The generated columns apply this policy consistently to existing and future cashouts.
- **Python typing.** `pyproject.toml` requires Python 3.13+ and configures Pyright in strict mode (`[tool.pyright] typeCheckingMode = "strict"`). Run `make typecheck` (backend Pyright + frontend `tsc`).
- **Lint/format.** Ruff for Python (with import sorting via `extend-select = ["I"]`), Prettier + ESLint for TS/React (the Tailwind plugin sorts classes).
- **Tests.** `make test` runs Vitest + Testing Library and the backend unit/integration suites. Integration tests use real Postgres and Redis via `TEST_DATABASE_URL` / `TEST_REDIS_URL` or throwaway testcontainers (Docker required), with provider clients faked. Dedicated tests also exercise the migration chain and the vendored OCR model. See [backend/tests/README.md](backend/tests/README.md) for fixture and tier details.

### Known incomplete work

Remaining work is tracked in [Planned scope](#planned-scope). The explicit configuration placeholder is:

- **Tipout rates are placeholders** — `core/config/tipout.py` ships stand-in rates (`TODO(tipout)`) for the four selectable departments, overridable via the `TIPOUT_*` variables; the manager's 1% is the real rate. The others must be set before the app reconciles a real cashout.

## License

Proprietary. Copyright © Whiskey District Inc. All rights reserved. See [LICENSE](LICENSE).
