# CLAUDE.md

Guidance for Claude Code sessions working on this repository. Keep it concise and project-specific. Update it when you discover a stable, reusable convention or non-obvious constraint.

## Project

**Whiskey District Cashout Automation** — internal restaurant ops tool. FastAPI backend + Vue 3 SPA, single origin in production (FastAPI serves the built frontend out of `backend/static/`). Deployed to Render at <https://cashout-ops.onrender.com>.

The cashout flow: a cashier creates a cashout submission (any time — cashouts are **not** shift-locked), uploads photos/PDFs of the end-of-shift documents (TouchBistro reports, terminal reports, receipts, tip-out sheets, cash summaries), and an **AI document pipeline** classifies each document and extracts structured data from it. Management reviews the extracted data and completes the submission.

The cross-cutting plumbing, auth, error contract, the AI extraction pipeline, and the full cashout domain are **implemented**. What remains stubbed with placeholder values: the **extraction schemas** (`features/cashout/extraction/schemas.py`) hold dummy fields — the real per-document observable fields are not defined yet — and the **frontend** is minimal.

## Layout

The backend is organized **by feature** under `app/features/<feature>/`; cross-cutting concerns live in `app/core`, `app/lib`, `app/errors`, `app/dependencies`, `app/integrations`, and `app/documents`.

```
backend/
  app/main.py             create_app(); `app = create_app()`; ASGI target is app.main:app; mounts StaticFiles + SPA fallback
  app/lifespan.py         lifespan/composition root: builds async engine + sessionmaker AND the document-AI clients on app.state
  app/core/               config (pydantic-settings), cookies (generic set/delete helpers), db/ (Base, Entity, enum_column, registry), schemas (BaseIn/BaseOut/EntityOut/UtcDateTime)
  app/lib/                pure helpers: casing, crypto, documents (DocumentContent/DocumentContentType)
  app/dependencies/       FastAPI deps: get_db, get_current_user, require_admin, require_csrf, get_cashout_document_processor, get_document_storage
  app/errors/             domain errors, catalog, handlers, translators, schemas, types, OpenAPI shapes
  app/integrations/       provider adapters:
    ai/                     AIClient protocol + Anthropic/OpenAI/Gemini clients (structured output), compose_instructions, AIProvider, AIAnalysisError
    storage/                DocumentStorageClient protocol + LocalDocumentStorageClient
  app/documents/          DocumentAIClient (generic classify + structured extraction over AIClient + storage), DocumentRef, DocumentClassification
  app/features/
    auth/                   passwords (bcrypt), service (login/register/authenticate/logout), router, schemas, types
    sessions/               model, service, cookies (session/CSRF cookie helpers), types
    users/                  model, service, router, schemas (UserOut/UserCreate), types (UserRole)
    cashout/                models/ (submission, document, analysis, data), service, router, schemas, types
      extraction/           CashoutDocumentProcessor, registry (type→schema), schemas (DUMMY fields — see below)
  app/api/__init__.py     mounts each feature router under /api
  migrations/             alembic (env.py reads DATABASE_URL, target = app.core.db.registry.metadata); versions/
  Makefile                uv-based dev tasks (install/run/format/lint/test/revision/migrate)
  tests/                  pytest suite (testcontainers Postgres); conftest, fakes, factories
frontend/                 Vue 3 SPA (minimal / WIP)
compose.yaml              Postgres 18 for local dev
scripts/                  Render deploy hooks (build / pre-deploy / start) — at the repo root
```

## Commands

Tooling is **uv** (see `uv.lock`) driven through the backend `Makefile`. Run backend targets from `backend/`:

```bash
make install                       # uv sync
make run                           # uvicorn app.main:app --reload
make migrate                       # alembic upgrade head
make revision MESSAGE="…"          # alembic revision --autogenerate -m "…"
make format                        # ruff format .
make lint                          # ruff check . --fix
make test                          # pytest
make check                         # format + lint + test
```

Frontend (from `frontend/`): `npm run dev|build|lint|format|test`. Database (repo root): `docker compose up -d` (Postgres 18 on :5432, user/pw postgres/dev, db cashout_ops).

## Environment

Backend loads from `backend/.env` via `pydantic-settings`. `.env` is gitignored; copy `backend/.env.example`. Variables (see `app/core/config.py`):

- `ENVIRONMENT` — `prod` (default) or `dev` (`Literal["prod", "dev"]`). Drives `settings.DEBUG` (`== "dev"`), which controls FastAPI debug mode and the `Secure` cookie flag (`Secure = not DEBUG`). **Use `dev`, not `development`.**
- `SECRET_KEY` — **required**; signs the Starlette `SessionMiddleware`.
- `DATABASE_URL` — **required**; async SQLAlchemy URL (`postgresql+psycopg://…`). Alembic reads the same var.
- `SESSION_TTL_DAYS` — default `7`.
- `ADMIN_EMAIL` — default `admin@test.com`. `auth.register` promotes a matching email to `UserRole.ADMIN`.
- `AI_PROVIDER` — `ANTHROPIC` (default), `OPENAI`, or `GEMINI`. Selects which client the lifespan builds. **Only the selected provider's API key is required** — the lifespan raises at startup if it's missing.
- `AI_MODEL` — default `claude-opus-4-8`. Set it to a model the selected provider serves.
- `AI_MAX_TOKENS` — default `16000`; passed to the client constructor.
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` — all optional at the settings layer; the one matching `AI_PROVIDER` is required at runtime. A placeholder lets the app boot; a real key is only needed to hit the extract endpoint.
- `DOCUMENT_STORAGE_DIR` — default `storage/documents`; where `LocalDocumentStorageClient` writes uploads.

## Architecture rules

### Transactions and where to commit

**`get_db` (`app/dependencies/db.py`) owns the transaction** — one `AsyncSession` per request, **commits if the handler returns successfully, rolls back if it raises**. Neither services nor routes call `db.commit()`.

**Services never commit.** They build/mutate ORM objects and either return them or raise a `DomainError`. A **create-style service must `await db.flush()`** before returning if the router will serialize the new object — flush populates the generated `id`, server defaults (`created_at`), and Python-side column defaults (enum `status`). Returning an unflushed object serializes to a `422` (and the response-validation error then rolls back the insert). Use keyword-only args after `db`.

### Errors

Always raise the domain errors from `app.errors` (subclasses of `DomainError`) — never `HTTPException`. Handlers in `app/errors/handlers.py` funnel domain errors + translated Pydantic / `IntegrityError` / Starlette HTTP / uncaught exceptions into one body: `{ "error", "code", "message", "errors" }`. `errors` is present only for `UNPROCESSABLE`. Don't hand-craft error JSON.

- Adding an error code: extend `ErrorCode` (types.py) + `CATALOG` entry (catalog.py) + `DomainError` subclass (domain.py) + export from `errors/__init__.py`. Conflicts (409) subclass `ConflictError`. `InvalidStateError` (409, `INVALID_STATE`) is used for wrong-lifecycle-state actions.
- `IntegrityError` auto-maps by SQLSTATE: unique → `ALREADY_EXISTS`, FK → `IN_USE`, check/not-null → `UnprocessableError`, else `ServerError`.

### API conventions

- Everything under `/api`. Register feature routers in `app/api/__init__.py`. CSRF/auth are **not** global — apply `require_csrf`, `get_current_user`, `require_admin` (from `app/dependencies`) per-route/router via `dependencies=[...]`.
- Inbound/outbound JSON is **camelCase**; Python is snake_case. Automatic via `BaseIn`/`BaseOut` (`alias_generator=snake_to_camel`). `BaseOut` sets `validate_by_name=True` + `from_attributes=True` so `model_validate(orm_obj)` reads snake_case attrs; FastAPI serializes out with `by_alias`. Don't rename fields by hand.
- `BaseIn` is `extra="forbid"` + `validate_by_name=True`. Keep `extra="forbid"`.
- Return a `BaseOut` model and let `response_model` serialize it. Timestamps: use the `UtcDateTime` annotated type (`app/core/schemas.py`) — stored UTC, serialized ISO-8601 with trailing `Z`.

### Auth and sessions

- Session token: `crypto.generate_secret_token()` = `secrets.token_urlsafe(32)`. Only the SHA-256 hash is stored in `sessions.token_hash`; compare by hashing. Session lifetime `SESSION_TTL_DAYS`; no "remember me". Passwords: bcrypt via `passlib` (`app/features/auth/passwords.py`).
- Cookies: generic `set_cookie`/`delete_cookie` in `app/core/cookies.py` (`Secure = not DEBUG`, `SameSite=Lax`, `Path=/`); named session/CSRF helpers in `app/features/sessions/cookies.py`. `session_token` is HttpOnly; `csrf_token` is JS-readable for the double-submit check (`x-csrf-token` header). `require_csrf` uses `secrets.compare_digest`.

### Document extraction pipeline

The AI reads the uploaded file directly (vision), classifies it, and returns structured data — there is **no OCR**. Layered so the domain never touches a provider SDK:

```
CashoutDocumentProcessor (features/cashout/extraction)  ← domain: maps DocumentClassification[CashoutDocumentType] → its schema
  → DocumentAIClient (app/documents)                    ← generic: classify() + process(), reads bytes from storage
      → AIClient protocol (app/integrations/ai)         ← AnthropicAIClient | OpenAIAIClient | GeminiAIClient (structured output)
      → DocumentStorageClient (app/integrations/storage) ← LocalDocumentStorageClient
```

- **Provider is swappable.** `AIClient` is a Protocol (`provider`, `model`, `analyze(content, response_model, *, instructions)`) with three implementations: `AnthropicAIClient` (Messages API `messages.parse`), `OpenAIAIClient` (Chat Completions `parse`), `GeminiAIClient` (`generate_content` + `response_schema`). `app/lifespan.py` `_build_ai_client()` picks one from `settings.AI_PROVIDER` and validates its key. All raise `AIAnalysisError` (code in `AIErrorCode`) on provider errors / refusals / invalid output; each maps text + image/PDF `DocumentContent` to its own request shape. The OpenAI/Gemini clients are tested against fakes only — not verified against live APIs.
- The clients are built once in `app/lifespan.py` and stored on `app.state`; routes get the processor/storage via `get_cashout_document_processor` / `get_document_storage`.
- **Instructions layer, they don't replace.** Each AI abstraction keeps its own always-present base instructions and appends the caller's `instructions` on top via `compose_instructions(base, extra)` (`integrations/ai/instructions.py`) — the `AnthropicAIClient` has a base persona, `DocumentAIClient` has base classify/extract instructions, and the processor passes domain-specific instructions as the extra. Don't reintroduce a "default OR override" pattern.
- **`classify` vs `process`.** `DocumentAIClient.classify` returns `DocumentClassification[EnumT]` (`value` + `confidence`). `DocumentAIClient.process` returns `DocumentAnalysis[ResponseModelT]` — the typed `data` plus an extraction `confidence` and a list of `FieldIssue` (`path`, `message`) the model flagged. The cashout service persists both confidences separately: `classification_confidence` and `extraction_confidence`, plus `issues` (JSONB) on `CashoutDocumentAnalysis`.
- `AnthropicAIClient.analyze` raises `AIAnalysisError` (code in `AIErrorCode`) on provider errors, refusals, or invalid/unparseable output. The cashout service catches it and persists a **FAILED, reviewable** `CashoutDocumentAnalysis` rather than 500-ing.
- `CashoutDocumentType.UNKNOWN` (or any type with no registered schema) is **not** an error: the processor returns it with `data=None` and the service records a failed analysis.
- **Extraction schemas are placeholders.** `features/cashout/extraction/schemas.py` defines dummy fields (marked with `TODO(document-ai)`) so the pipeline runs end to end. Define the real per-document fields before trusting extracted data. Deterministic post-extraction validation and real reconciliation in `service._reconcile` are also still TODO.

### Models

- All entities inherit `Entity` from `app/core/db/models.py` (`id`, `created_at`, `await Entity.get_active(db, id_)` → `NotFoundError` on miss). `enum_column(enum_cls, name)` builds a native Postgres enum persisting member **values**.
- Models: `User`, `Session`, `CashoutSubmission`, `CashoutDocument`, `CashoutDocumentAnalysis`, `CashoutData`. (The `Shift` model and shifts feature were removed — cashouts are no longer shift-locked.)
- **Adding a model:** create it in the feature package, then **import it in `app/core/db/registry.py`** (Alembic autogenerate and the test schema both read `registry.metadata` — a model missing from the registry is invisible to both). Then `make revision MESSAGE="…"` and review the diff.

### Authorization

Explicit FastAPI deps in `app/dependencies/` (`get_current_user`, `require_admin`, `require_csrf`). Resource/owner checks live in the cashout **service** (`_get_owned_submission`, and `get_submission` allows owner-or-admin) since they need the loaded row.

## Migrations

- Single initial migration `migrations/versions/cbf386fc33b2_initial_schema.py`. `env.py` targets `app.core.db.registry.metadata`. `alembic.ini` `script_location` is `migrations/` (flat — no nested `alembic/` dir).
- **Native-enum downgrade gotcha:** autogenerate creates enum types but never drops them, so a re-upgrade fails with "type already exists". The initial migration's `downgrade()` drops each enum explicitly (`ENUM_TYPES` list) — do the same in any migration that adds an enum column.

## Testing

- `make test` / `pytest`. Async tests via `pytest-asyncio` (`asyncio_mode = "auto"`). Config in `pyproject.toml` (`[tool.pytest.ini_options]`, `pythonpath = ["."]`).
- **Real Postgres, not SQLite** (native enums/JSONB/FKs). `tests/conftest.py` uses `TEST_DATABASE_URL` if set, else spins up a throwaway Postgres via **testcontainers** (Ryuk disabled; requires a running Docker). Schema via `registry.metadata.create_all`; tables truncated between tests.
- The extraction stack is **real** in tests; only the AI provider and object store are faked (`tests/fakes.py`: `FakeAIClient`, `FakeDocumentStorage`). API tests override `get_db`/`get_cashout_document_processor`/`get_document_storage` and drive the app over `httpx.ASGITransport`.
- Fixtures: `client` (unauthed), `cashier_client`, `admin_client`, `db_session`, `ai_client`, `storage`, `processor`. Helpers in `tests/factories.py` (`register`, `login`, `csrf_headers`). Configure `ai_client.classification` / `.extraction` / `.error` to steer the pipeline.

## Deployment

Render uses three repo-root scripts: `build.bash` (backend `make install`, then `npm ci && npm run build`), `pre-deploy.bash` (`make migrate`), `start.bash` (`gunicorn -k uvicorn.workers.UvicornWorker app.main:app`). If you change the dependency surface, install path, or migration assumptions, update the matching script.

## Rules for editing

- Repo runs **Pylance/pyright strict** (`.vscode/settings.json`). Don't add `# type: ignore` to silence real errors in `app/`. Sanctioned ignores: `reportUnusedFunction` on decorated FastAPI handlers, `reportCallIssue` on `Settings()`. Test files use a few targeted ignores for untyped test libs (testcontainers). Pyright is an IDE aid — the gate is `make check` (ruff + pytest).
- Dependencies live in `pyproject.toml`, managed by **uv** (`uv.lock`) — no `requirements.txt`. Don't switch off `psycopg` 3 / `postgresql+psycopg://`.
- Don't bypass `BaseIn`/`BaseOut` (skips validation + casing). Don't catch `Exception` in services to "convert" it — handlers already have a catch-all + `IntegrityError` handler. Don't add CORS (single-origin by design; use a Vite proxy for dev).
- Files to read before editing related code: routes → `app/api/__init__.py`, `app/dependencies/`; services → `app/features/*/service.py` templates + `app/dependencies/db.py` (commit semantics); models → `app/core/db/models.py`, `app/core/db/registry.py`; schemas → `app/core/schemas.py`, `app/lib/casing.py`; extraction → `app/documents/`, `app/integrations/`, `app/features/cashout/extraction/`; errors → `app/errors/`; migrations → `app/core/db/registry.py`, `migrations/env.py`.

## Known bugs / gotchas

The previously-tracked scaffold bugs (broken first migration, `start.bash` ASGI target, `.env.example` `ENVIRONMENT=production`, `vite-end.d.ts` typo, missing `bcrypt` dependency) are **fixed**. Remaining known-incomplete work:

1. **Extraction schemas are dummy fields** — see the Document extraction pipeline section. Real fields, deterministic validation, and `service._reconcile` are TODO.
2. **`LocalDocumentStorageClient` is not durable on Render** (ephemeral disk) — swap in an object-store client before relying on uploaded files surviving a deploy.
3. **Frontend is minimal / WIP.**
