# CLAUDE.md

Guidance for Claude Code sessions working on this repository. Keep it concise and project-specific. Update it when you discover a stable, reusable convention or non-obvious constraint.

## Project

**Whiskey District Cashout Automation** — internal restaurant ops tool. FastAPI backend + React 19 SPA, single origin in production (FastAPI serves the built frontend out of `backend/static/`). Deployed to Render at <https://cashout-ops.onrender.com>.

The cashout flow: a cashier creates a cashout submission (any time — cashouts are **not** shift-locked) and uploads photos/PDFs of the end-of-shift documents (TouchBistro reports, terminal reports, receipts, tip-out sheets, cash summaries). Upload returns an `EXTRACTING` analysis immediately; the **AI document pipeline** classifies + extracts in a post-commit background job and the client polls `GET /cashout/analyses/{id}` until `NEEDS_VERIFICATION` (or `FAILED`, retryable via extract). The cashier **verifies** each analysis (optionally submitting corrected values → `verified_data_json`), then completes the submission, which reconciles the verified analyses into `CashoutData` (`PROCESSING` → `COMPLETED`).

The cross-cutting plumbing, auth, error contract, the AI extraction pipeline, and the full cashout domain are **implemented**. What remains stubbed with placeholder values: the **extraction schemas** (`features/cashout/extraction/schemas.py`) hold dummy fields — the real per-document observable fields are not defined yet — and the **frontend** is a first-pass frame (contracts + wiring done; visual polish pending).

## Layout

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/lib`, `app/errors`, `app/dependencies`, `app/integrations`, and `app/documents`.

```
backend/
  app/main.py             create_app(); `app = create_app()`; ASGI target is app.main:app; mounts StaticFiles + SPA fallback
  app/lifespan.py         lifespan/composition root: builds async engine + sessionmaker AND the document-AI clients on app.state
  app/core/               config (pydantic-settings), cookies (generic set/delete helpers), db/ (Base, Entity, enum_column, registry), schemas (BaseIn/BaseOut/EntityOut/UtcDateTime)
  app/lib/                pure helpers: casing, crypto, documents (DocumentContent/DocumentContentType)
  app/dependencies/       FastAPI deps, one module per concern: db (get_db, get_db_sessionmaker), background (get_post_commit_tasks), auth (get_current_user, require_admin, require_verified_user), csrf (require_csrf), email (get_email_client), storage (get_document_storage), processor (get_cashout_document_processor) — all re-exported from the package
  app/errors/             error framework: contracts (types features use), codes/catalog/constraints (aggregators), app_error (AppError), validation/ (ValidationError + issue catalog), translators, handlers, schemas, openapi
  app/integrations/       provider adapters:
    ai/                     AIClient protocol + Anthropic/OpenAI/Gemini clients (structured output), compose_instructions, AIProvider, AIAnalysisError
    storage/                DocumentStorageClient protocol + LocalDocumentStorageClient
    email/                  EmailClient protocol + ResendEmailClient / ConsoleEmailClient (logs), EmailProvider; picked by EMAIL_PROVIDER
  app/documents/          DocumentAIClient (generic classify + structured extraction over AIClient + storage), DocumentRef, DocumentClassification
  app/features/
    auth/                   passwords (bcrypt), service (login/register/authenticate/logout), router, schemas, errors, types
    sessions/               model, service, cookies (session/CSRF cookie helpers), types
    users/                  model, service (list_users, create, bootstrap_admin), router (/me + admin list), schemas (UserOut/UserCreate), errors, types (UserRole)
    invitations/            model, service (list/create/is_invited/mark_accepted/delete), router (admin-only), schemas, errors
    email_verification/     model (one row per user), service (send_new_code post-commit job; verify_email on get_db), router (verify/resend), schemas, errors, templates/ (verify_email.html)
    cashout/                models/ (submission, document, analysis, data), service, router, schemas, errors, analysis_errors (messages for FAILED analyses), types
      extraction/           CashoutDocumentProcessor, registry (type→schema), schemas (DUMMY fields — see below)
  app/api/__init__.py     mounts each feature router under /api
  migrations/             alembic (env.py reads DATABASE_URL, target = app.core.db.registry.metadata); versions/
  tests/                  pytest suite (testcontainers Postgres); conftest, fakes, factories
frontend/                 React 19 SPA (TypeScript, Vite, Tailwind v4, TanStack Query, React Router)
  src/api/                typed contracts (types.ts) + fetch client (CSRF header, error contract → ApiError) + per-feature endpoint modules
  src/auth/               AuthProvider (["me"] query), RequireAuth/RequireAdmin guards, login/register, EmailVerificationGate (blocking modal for accounts with null emailVerifiedAt; wired to verify/resend)
  src/styles/global.css   ALL color tokens (light + dark, accent) — components use semantic utilities (bg-surface, text-ink, bg-accent…), never raw colors
  src/components/ui.tsx   shared primitives; src/layout/AppLayout.tsx mobile-first shell (bottom nav < md)
  src/features/           cashout/ (cashier flow: upload → poll analysis → verify → complete), admin/ (submissions + data tables, users page: accounts + invitation management)
compose.yaml              Postgres 18 for local dev
scripts/                  Render deploy hooks (build / pre-deploy / start) — at the repo root
Makefile                  repo-root orchestration — calls uv directly against backend/pyproject.toml (no backend/Makefile)
```

## Commands

Tooling is **uv** (see `uv.lock`), driven through the repo-root `Makefile` — there is no `backend/Makefile`; backend targets run `uv --directory backend ...` directly. Run from the repo root:

```bash
make backend-install               # uv sync
make backend-dev                   # uv run fastapi dev
make backend-migrate               # alembic upgrade head
make backend-revision MESSAGE="…"  # alembic revision --autogenerate -m "…"
make backend-format                # ruff format .
make backend-lint                  # ruff check . --fix
make backend-test                  # pytest
make backend-check                 # format + lint + test
```

Frontend: `make frontend-dev|frontend-build|frontend-lint|frontend-format|frontend-test` (or from `frontend/`: `npm run dev|build|lint|format|test`). Database: `make db-up|db-down|db-logs` (Postgres 18 on :5432, user/pw postgres/dev, db cashout_ops). Aggregate targets `install|format|lint|test|check` run backend + frontend together.

## Environment

Backend loads from `backend/.env` via `pydantic-settings`. `.env` is gitignored; copy `backend/.env.example`. Variables (see `app/core/config.py`):

- `ENVIRONMENT` — `prod` (default) or `dev` (`Literal["prod", "dev"]`). Drives `settings.DEBUG` (`== "dev"`), which controls FastAPI debug mode and the `Secure` cookie flag (`Secure = not DEBUG`). **Use `dev`, not `development`.**
- `DATABASE_URL` — **required**; async SQLAlchemy URL (`postgresql+psycopg://…`). Alembic reads the same var.
- `SESSION_TTL_DAYS` — default `7`.
- `INVITATION_TTL_DAYS` — default `7`; how long an invitation stays acceptable.
- `ADMIN_EMAIL` — default `admin@test.com`. `auth.register` routes a matching email to `users_service.bootstrap_admin` (created with `UserRole.ADMIN`, no invitation required). Every other registration requires a pending (unaccepted, unexpired) invitation, which registering marks accepted. Registration is otherwise untouched by email verification (see below).
- **Email** — `EMAIL_PROVIDER` (`CONSOLE` default, or `RESEND`) selects the client the lifespan builds, mirroring `AI_PROVIDER`. `CONSOLE` (`ConsoleEmailClient`) logs the message and boots without a key; `RESEND` (`ResendEmailClient`) sends for real and the lifespan **raises at startup if `RESEND_API_KEY` is missing**. `EMAIL_FROM` (default `Whiskey District <onboarding@resend.dev>`) is the sender.
- **Email verification** — `EMAIL_VERIFICATION_CODE_TTL_MINUTES` (15). A numeric code is emailed **after** registration commits via a post-commit job (`email_verification_service.send_new_code`, which issues the single per-user code row and sends it through the injected `EmailClient`); `email_verified_at` on `User` gates the account (the frontend `EmailVerificationGate`) until confirmed via `POST /api/email-verification/verify` (`verify_email`, on `get_db`). `POST /resend` re-queues `send_new_code`. `require_verified_user` (`app/dependencies/auth.py`) raises `EMAIL_NOT_VERIFIED` (403) for an unverified user and **guards every authenticated route** — applied at the router level on cashout and invitations, and per-route on the users list. **Exempt** (reachable while unverified): `GET /users/me`, all auth routes, and all email-verification routes. The frontend `EmailVerificationGate` blocks the UI in parallel, and re-runs its queries once verification succeeds.
- `AI_PROVIDER` — `ANTHROPIC` (default), `OPENAI`, or `GEMINI`. Selects which client the lifespan builds. **Only the selected provider's API key is required** — the lifespan raises at startup if it's missing.
- **AI model** — not an env var. `Settings.AI_MODELS` (`app/core/config.py`) maps each `AIProvider` to its model (`claude-sonnet-4-6` / `gpt-5.6-terra` / `gemini-3.5-flash`); the `AI_MODEL` computed field resolves the entry for `AI_PROVIDER`. Change a provider's model by editing that map.
- `AI_CLASSIFICATION_MAX_TOKENS` / `AI_EXTRACTION_MAX_TOKENS` — defaults `512` / `2048`; per-operation output-token budgets held by `DocumentAIClient` and passed per `analyze` call (classification is a tiny fixed-shape object; extraction scales with the schema). Deliberately conservative — raise them if analyses fail with the `TRUNCATED` error code.
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` — all optional at the settings layer; the one matching `AI_PROVIDER` is required at runtime. A placeholder lets the app boot; a real key is only needed to hit the extract endpoint.
- `DOCUMENT_STORAGE_DIR` — default `storage/documents`; where `LocalDocumentStorageClient` writes uploads.

## Architecture rules

### Transactions and where to commit

**`get_db` (`app/dependencies/db.py`) owns the transaction** — one `AsyncSession` per request, **commits if the handler returns successfully, rolls back if it raises**. Neither services nor routes call `db.commit()`.

**Services never commit.** They build/mutate ORM objects and either return them or raise an `AppError`. A **create-style service must `await db.flush()`** before returning if the router will serialize the new object — flush populates the generated `id`, server defaults (`created_at`), and Python-side column defaults (enum `status`). Returning an unflushed object serializes to a `422` (and the response-validation error then rolls back the insert). Use keyword-only args after `db`.

**One sanctioned exception — post-commit background jobs.** Starlette `BackgroundTasks` run *before* the `get_db` teardown commit in this stack, so they can't see the request's writes. Long work that must observe them (AI extraction) is queued on `PostCommitTasks` (`app/dependencies/background.py`) and runs in its teardown; the dependency **must be listed first** in the router's `dependencies=[...]` (teardown is LIFO) so it fires after the commit. The job builds its own session from `get_db_sessionmaker` and commits it (see `cashout_service.run_extraction`). Issuing + emailing the verification code (`email_verification_service.send_new_code`, queued by register and `/resend`) uses the same mechanism — it owns its session and sends through the injected `EmailClient`.

### Errors

Always raise `AppError` from `app.errors` — never `HTTPException`. `AppError(code, message=None)`: `code` is a string literal from the catalog; `message` is **internal-only** context (logs/tracebacks) — the response message is always the catalog default for the code, never the instance message. Keep an originating exception via `raise AppError(...) from exc`. Handlers in `app/errors/handlers.py` funnel app errors + translated Pydantic / `RequestValidationError` / `IntegrityError` / Starlette HTTP / uncaught exceptions into one body: `{ "kind", "code", "message", "issues" }`; `issues` is present only for validation failures (`kind: "VALIDATION"`). Don't hand-craft error JSON.

- **Each feature owns its codes** in `app/features/<feature>/errors.py`: a `<Feature>ErrorCode` Literal, a `<feature>_error_catalog` (kind + default message per code), and optionally `<feature>_constraint_to_code` mapping DB constraint/index names to codes (unique violations report the *index* name, e.g. `ix_users_email`). Feature error modules import only `app.errors.contracts`.
- **`app/errors` aggregates:** `contracts.py` holds the types features use (`ErrorKind`, `ErrorCatalog`, `ConstraintToCode`); `codes.py` unions base + feature codes into `ErrorCode`; `catalog.py` merges the catalogs and maps `kind_to_status` (the only place statuses live — a code's HTTP status always derives from its kind); `constraints.py` merges the constraint maps. Cross-cutting base codes (`INTERNAL`, `BAD_REQUEST`, `VALIDATION_FAILED`, `UNAUTHENTICATED`, `FORBIDDEN`, `ROUTE_NOT_FOUND`, `CONFLICT`, `SERVICE_UNAVAILABLE`) live in `codes.py`/`catalog.py` directly. There is **no generic `NOT_FOUND` code** — a missing entity uses its feature's specific code (`USER_NOT_FOUND`, `INVITATION_NOT_FOUND`, `SUBMISSION_NOT_FOUND`, `DOCUMENT_NOT_FOUND`, `ANALYSIS_NOT_FOUND`); `ROUTE_NOT_FOUND` is only for unknown API paths (SPA catch-all, Starlette 404s).
- Adding a feature code: extend the feature's Literal + catalog (+ constraint map if DB-enforced). A new feature's exports must also be wired into `codes.py`, `catalog.py`, and `constraints.py`.
- **Validation:** `ValidationError` (an `AppError` with code `VALIDATION_FAILED`, `app/errors/validation/`) carries `issues` (`{code, path, ctx}`); response messages come from `validation_issue_catalog`. `translate_validation_error` converts Pydantic/FastAPI validation errors (camelCasing paths, stripping the `body`/`query`/... prefix); `translate_integrity_error` looks up the violated constraint in `constraint_to_code`, falling back by SQLSTATE class (unique/FK/restrict → `CONFLICT`, check/not-null → `VALIDATION_FAILED`, else `INTERNAL`).
- **`app/errors/__init__` is deliberately minimal** (`AppError`, `ValidationError` only): feature error modules initialize the package via `app.errors.contracts`, so pulling the aggregators into the init would be a circular import. Import `error_responses` from `app.errors.openapi` and `init_error_handlers` from `app.errors.handlers`.
- **OpenAPI:** document each route's error codes with `error_responses(*codes)` (`app/errors/openapi.py`) passed as `responses=` on the router (shared codes like `UNAUTHENTICATED`/`INVALID_CSRF_TOKEN`) or route; codes sharing a status merge into one response with an example per code. The app level registers only `INTERNAL`. Supplying `VALIDATION_FAILED` this way also replaces FastAPI's default `HTTPValidationError` schema — never let that default leak into the docs.

### API conventions

- Everything under `/api`. Register feature routers in `app/api/__init__.py`. CSRF/auth are **not** global — apply `require_csrf`, `get_current_user`, `require_admin` (from `app/dependencies`) per-route/router via `dependencies=[...]`.
- Inbound/outbound JSON is **camelCase**; Python is snake_case. Automatic via `BaseIn`/`BaseOut` (`alias_generator=snake_to_camel`). `BaseOut` sets `validate_by_name=True` + `from_attributes=True` so `model_validate(orm_obj)` reads snake_case attrs; FastAPI serializes out with `by_alias`. Don't rename fields by hand.
- `BaseIn` is `extra="forbid"` + `validate_by_name=True`. Keep `extra="forbid"`.
- Return a `BaseOut` model and let `response_model` serialize it. Timestamps: use the `UtcDateTime` annotated type (`app/core/schemas.py`) — stored UTC, serialized ISO-8601 with trailing `Z`.
- Status codes: resource-creating POSTs return **201** (upload returns the created **analysis** in `EXTRACTING`; the client polls it); body-less actions (logout) return **204**; RPC-style actions that return the updated resource (extract/verify/complete) return 200. Give every handler a short docstring — it becomes the OpenAPI operation description.
- Cashout paths are explicit per resource under `/api/cashout`: `/cashout/submissions…`, `/cashout/documents/{id}/extract`, `/cashout/analyses/{id}[/verify]`.
- The SPA catch-all in `app/main.py` is `include_in_schema=False` and returns a JSON 404 for unknown `/api/*` paths instead of the SPA shell.

### Auth and sessions

- Session token: `crypto.generate_secret_token()` = `secrets.token_urlsafe(32)`. Only the SHA-256 hash is stored in `sessions.token_hash`; compare by hashing. Session lifetime `SESSION_TTL_DAYS`; no "remember me". Passwords: bcrypt via `passlib` (`app/features/auth/passwords.py`).
- Cookies: generic `set_cookie`/`delete_cookie` in `app/core/cookies.py` (`Secure = not DEBUG`, `SameSite=Lax`, `Path=/`); named session/CSRF helpers in `app/features/sessions/cookies.py`. `session_token` is HttpOnly; `csrf_token` is JS-readable for the double-submit check (`x-csrf-token` header). `require_csrf` uses `secrets.compare_digest`.

### Document extraction pipeline

The AI reads the uploaded file directly (vision), classifies it, and returns structured data — there is **no OCR**. Layered so the domain never touches a provider SDK:

```
CashoutDocumentProcessor (features/cashout/extraction)  ← domain: maps DocumentClassification[CashoutDocumentClassification] → its schema
  → DocumentAIClient (app/documents)                    ← generic: classify() + process(), reads bytes from storage
      → AIClient protocol (app/integrations/ai)         ← AnthropicAIClient | OpenAIAIClient | GeminiAIClient (structured output)
      → DocumentStorageClient (app/integrations/storage) ← LocalDocumentStorageClient
```

- **Provider is swappable.** `AIClient` is a Protocol (`provider`, `model`, `analyze(content, response_model, *, instructions, max_tokens)`) with three implementations: `AnthropicAIClient` (Messages API `messages.parse`), `OpenAIAIClient` (Chat Completions `parse`), `GeminiAIClient` (`generate_content` + `response_json_schema` — **not** `response_schema`: the response models set `extra="forbid"`, whose JSON schema carries `additionalProperties`, which `response_schema` rejects; the SDK therefore returns `response.parsed` as a dict and the client runs `model_validate` itself). `app/lifespan.py` `_build_ai_client()` picks one from `settings.AI_PROVIDER` and validates its key. All raise `AIAnalysisError` (code in `AIErrorCode`) on provider errors / refusals / truncated output (max-tokens, `TRUNCATED`) / invalid output; each maps text + image/PDF `DocumentContent` to its own request shape. The OpenAI/Gemini clients are tested against fakes only — not verified against live APIs.
- The clients are built once in `app/lifespan.py` and stored on `app.state`; routes get the processor/storage via `get_cashout_document_processor` / `get_document_storage`.
- **Instructions layer, they don't replace.** Each AI abstraction keeps its own always-present base instructions and appends the caller's `instructions` on top via `compose_instructions(base, extra)` (`integrations/ai/instructions.py`) — the `AnthropicAIClient` has a base persona, `DocumentAIClient` has base classify/extract instructions, and the processor passes domain-specific instructions as the extra. Don't reintroduce a "default OR override" pattern.
- **`classify` vs `process`.** `DocumentAIClient.classify` returns `DocumentClassification[EnumT]` (`value` + `confidence`). `DocumentAIClient.process` returns `DocumentAnalysis[ResponseModelT]` — the typed `data` plus an extraction `confidence` and a list of `FieldIssue` (`path`, `message`) the model flagged. The cashout service persists both confidences separately: `classification_confidence` and `extraction_confidence`, plus `issues` (JSONB) on `CashoutDocumentAnalysis`.
- `AnthropicAIClient.analyze` raises `AIAnalysisError` (code in `AIErrorCode`) on provider errors, refusals, or invalid/unparseable output. The extraction job catches it and marks the `CashoutDocumentAnalysis` `FAILED` with `error_code` (the `AIErrorCode` value) and a safe mapped `error_message` (retryable via the extract endpoint). Unexpected job crashes are marked `FAILED` with a null `error_code` and the generic default message, so an analysis never sits in `EXTRACTING` forever — there is no separate analysis-level error-code enum.
- An **unclassifiable** document is **not** an error: `CashoutDocumentClassification` has an explicit `UNKNOWN` member the model can pick (the processor also folds a null `DocumentClassification.value` into it), `UNKNOWN` has no schema in the extraction registry, so the processor returns `data=None` and the analysis completes as `NEEDS_VERIFICATION` with `classification = UNKNOWN` and no extracted data. A completed analysis therefore always has a non-null classification. The classified type lives only on `CashoutDocumentAnalysis.classification`; `CashoutDocument` has no `document_type`.
- **Extraction schemas are placeholders.** `features/cashout/extraction/schemas.py` defines dummy fields (marked with `TODO(document-ai)`) so the pipeline runs end to end. Define the real per-document fields before trusting extracted data. Deterministic post-extraction validation and real reconciliation in `service._reconcile` are also still TODO.

### Models

- All entities inherit `Entity` from `app/core/db/models.py` (`id`, `created_at`, `await Entity.find_by_id(db, id_)` → `Self | None`; the calling service checks for `None` and raises its feature's `*_NOT_FOUND` code). `enum_column(enum_cls, name)` builds a native Postgres enum persisting member **values**.
- Models: `User`, `Session`, `Invitation`, `EmailVerification`, `CashoutSubmission`, `CashoutDocument`, `CashoutDocumentAnalysis`, `CashoutData`. (The `Shift` model and shifts feature were removed — cashouts are no longer shift-locked.)
- **Adding a model:** create it in the feature package, then **import it in `app/core/db/registry.py`** (Alembic autogenerate and the test schema both read `registry.metadata` — a model missing from the registry is invisible to both). Then `make backend-revision MESSAGE="…"` and review the diff.

### Authorization

Explicit FastAPI deps in `app/dependencies/` (`get_current_user`, `require_admin`, `require_csrf`). Resource/owner checks live in the cashout **service** (`_get_owned_submission`, and `get_submission` allows owner-or-admin) since they need the loaded row.

## Migrations

- Single initial migration `migrations/versions/cbf386fc33b2_initial_schema.py`. `env.py` targets `app.core.db.registry.metadata`. `alembic.ini` `script_location` is `migrations/` (flat — no nested `alembic/` dir).
- **Native-enum downgrade gotcha:** autogenerate creates enum types but never drops them, so a re-upgrade fails with "type already exists". The initial migration's `downgrade()` drops each enum explicitly (`ENUM_TYPES` list) — do the same in any migration that adds an enum column.

## Testing

- `make backend-test` / `pytest`. Async tests via `pytest-asyncio` (`asyncio_mode = "auto"`). Config in `pyproject.toml` (`[tool.pytest.ini_options]`, `pythonpath = ["."]`).
- **Real Postgres, not SQLite** (native enums/JSONB/FKs). `tests/conftest.py` uses `TEST_DATABASE_URL` if set, else spins up a throwaway Postgres via **testcontainers** (Ryuk disabled; requires a running Docker). Schema via `registry.metadata.create_all`; tables truncated between tests.
- The extraction stack is **real** in tests; only the AI provider and object store are faked (`tests/fakes.py`: `FakeAIClient`, `FakeDocumentStorage`). API tests override `get_db`/`get_cashout_document_processor`/`get_document_storage` and drive the app over `httpx.ASGITransport`.
- Fixtures: `client` (unauthed), `cashier_client`, `admin_client`, `db_session`, `ai_client`, `storage`, `processor`. Helpers in `tests/factories.py` (`register`, `login`, `csrf_headers`). Configure `ai_client.classification` / `.extraction` / `.error` to steer the pipeline.

## Deployment

Render uses three repo-root scripts: `build.bash` (`uv sync` in `backend/`, then `npm ci && npm run build`), `pre-deploy.bash` (`uv run alembic upgrade head` in `backend/`), `start.bash` (`gunicorn -k uvicorn.workers.UvicornWorker app.main:app`). These call `uv` directly rather than going through the root `Makefile`. If you change the dependency surface, install path, or migration assumptions, update the matching script.

## Rules for editing

- Repo runs **Pylance/pyright strict** (`.vscode/settings.json`). Don't add `# type: ignore` to silence real errors in `app/`. Sanctioned ignores: `reportUnusedFunction` on decorated FastAPI handlers, `reportCallIssue` on `Settings()`, `reportUnknownMemberType` on `genai...generate_content` in `integrations/ai/gemini.py` (google-genai rebinds its `PartUnion` type alias inside a runtime `if`, so pyright can't resolve it). Test files use a few targeted ignores for untyped test libs (testcontainers). Pyright is an IDE aid — the gate is `make check` (ruff + pytest).
- Dependencies live in `pyproject.toml`, managed by **uv** (`uv.lock`) — no `requirements.txt`. Don't switch off `psycopg` 3 / `postgresql+psycopg://`.
- Don't bypass `BaseIn`/`BaseOut` (skips validation + casing). Don't catch `Exception` in services to "convert" it — handlers already have a catch-all + `IntegrityError` handler. Don't add CORS (single-origin by design; use a Vite proxy for dev).
- Files to read before editing related code: routes → `app/api/__init__.py`, `app/dependencies/`; services → `app/features/*/service.py` templates + `app/dependencies/db.py` (commit semantics); models → `app/core/db/models.py`, `app/core/db/registry.py`; schemas → `app/core/schemas.py`, `app/lib/casing.py`; extraction → `app/documents/`, `app/integrations/`, `app/features/cashout/extraction/`; errors → `app/errors/`; migrations → `app/core/db/registry.py`, `migrations/env.py`.

## Known bugs / gotchas

The previously-tracked scaffold bugs (broken first migration, `start.bash` ASGI target, `.env.example` `ENVIRONMENT=production`, `vite-end.d.ts` typo, missing `bcrypt` dependency) are **fixed**. Remaining known-incomplete work:

1. **Extraction schemas are dummy fields** — see the Document extraction pipeline section. Real fields, deterministic validation, and `service._reconcile` are TODO.
2. **`LocalDocumentStorageClient` is not durable on Render** (ephemeral disk) — swap in an object-store client before relying on uploaded files surviving a deploy.
3. **Frontend is a first-pass frame** — flows work end to end (mobile-first), but visual polish, drag-and-drop uploads, and schema-specific correction editors are pending. Design rules: mobile first; all colors via the tokens in `src/styles/global.css`; API calls only through `src/api/*` (never raw `fetch`).
