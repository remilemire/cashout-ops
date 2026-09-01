# AGENTS.md

## Project

Cashout Ops is a full-stack application for submitting restaurant cashout documents, extracting structured data with AI, verifying the extracted data, and reviewing submissions through cashier and admin workflows.

The repository is the source of truth. Inspect existing implementations and nearby conventions before making changes.

## Working Principles

* Understand the relevant code path before editing it.
* Follow established project patterns unless the task explicitly requires changing them.
* Prefer the smallest coherent change that fully solves the requested task.
* Do not perform unrelated refactors.
* Do not invent abstractions, modules, endpoints, or configuration without first checking for an existing equivalent.
* Preserve existing public behavior unless the task explicitly changes it.
* Point out architectural inconsistencies rather than silently extending them.
* Do not make commits unless explicitly authorized.

## Repository Structure

* `backend/app/main.py` creates the FastAPI application, exposes `app.main:app`, and serves the built SPA.
* `backend/app/lifespan.py` is the composition root for the database engine, Redis client, and external clients stored on `app.state`; it orchestrates the per-component `lifespan.py` modules in `integrations/` and `infrastructure/`.
* `backend/app/core/` contains configuration (`config/`: the `Settings` root plus one nested settings group per concern — `app`, `db`, `redis`, `bootstrap`, `auth`, `email`, `ai`, `storage`, `outbox`, `rate_limit`, `tipout` — each in its own module), the external-provider enums (`providers.py`: `AIProvider`, `EmailProvider`, `StorageProvider`), the AI model catalog (`ai_models.py`: `AI_PROVIDER_MODELS`, which `AI_MODEL` is validated against), cookies, logging, and shared schemas.
* `backend/app/infrastructure/` contains low-level infrastructure such as the database foundations (`db/`: Base, registry, the `get_db` dependency), the Redis client (`redis/`: the `Redis` type, its lifespan, and the `get_redis` dependency), and the transactional outbox (`outbox/`: dispatcher, worker pool, messages).
* `backend/app/lib/` contains pure helpers such as casing and document utilities.
* `backend/app/security/` contains CSRF cookie helpers, secret-token cryptography, the `require_csrf` dependency, and the Redis fixed-window rate limiter (`rate_limit/`: `enforce` plus the `rate_limit_ip` dependency factory; feature-keyed limit dependencies live beside their feature). Session cookie helpers live with the sessions sub-feature in `features/auth/sessions/`.
* `backend/app/errors/` contains domain errors, handlers, translators, and OpenAPI error shapes.
* `backend/app/integrations/` contains the external provider clients — `ai/`, `email/`, `oauth/` (the Authlib registry and the `OAuthIssuer` enum), and `storage/` — each with its own `dependencies.py` (e.g. `email/`'s `get_email_client`, `storage/`'s `get_document_storage`).
* `backend/app/document_ai/` contains generic document classification and extraction behavior.
* `backend/app/features/` contains feature modules such as auth (with its `sessions/`, `email_challenges/`, and `oauth/` submodules — the last owning `oauth/external_identities/`, which maps issuer identities to local accounts and is private to the OAuth flow, plus `shared/`, which holds only what both sign-in flows use: `access.py` for granting and revoking sign-in at the HTTP boundary, and `accounts.py` for resolving a mailbox-proven address to a local account), users, and cashout (namespaced like auth into `submissions/`, `documents/`, `analyses/`, and `data/` sub-features — each owning its model, repository, service, schemas, and routes — plus `shared/`, which holds the single submission access policy (`access.py`) and the document-intake workflow (`workflows.py`) that coordinates across sub-features; the root `router.py` aggregates the sub-feature routers and also declares the cross-sub-feature workflow routes (document upload, manual-entry upload, re-extraction, and manual entry on an existing document) that call `shared/workflows.py`, while `errors.py`, `models.py`, and `outbox.py` are thin aggregation surfaces). `features/auth/dependencies.py` holds `get_current_user`, `require_admin`, and `require_owner`.
* `backend/app/features/cashout/extraction/` is a leaf sub-feature beside the others: cashout-specific document processing, extraction schemas, processor registration, and the `get_cashout_document_processor` dependency.
* `backend/app/api/__init__.py` mounts feature routers under `/api`.
* `frontend/src/api/` contains the fetch client, CSRF handling, the shared error contract, and typed API contracts.
* `frontend/src/auth/` contains authentication state, guards, and the passwordless login pages (email entry, code entry).
* `frontend/src/features/cashout/` contains the cashier submission workflow.
* `frontend/src/features/admin/` contains the admin submission, cashout-data, and user-management workflows.
* `frontend/src/components/` contains shared UI primitives (`ui.tsx`) alongside the dialog and confirm-dialog components.
* `frontend/src/styles/global.css` owns centralized light and dark theme tokens.

## Commands

Run repository-wide commands from the repository root.

### Setup and aggregate commands

* Install all dependencies: `make install`
* Format everything: `make format`
* Lint everything: `make lint`
* Typecheck everything: `make typecheck`
* Test everything: `make test`
* Run all checks: `make check`
* Apply database migrations: `make migrate`
* Delete generated caches: `make clean` (leaves `.env`, `backend/storage`, `backend/static`, `backend/.venv`, and `frontend/node_modules` intact)

### Backend

* Install dependencies: `make backend-install`
* Start the development API: `make backend-dev`
* Format: `make backend-format`
* Lint with fixes: `make backend-lint`
* Typecheck (Pyright strict): `make backend-typecheck`
* Test: `make backend-test` (`make backend-test-unit` / `make backend-test-integration` for a single tier)
* Run backend checks: `make backend-check`
* Apply migrations: `make backend-migrate`
* Generate a migration:
  `make backend-revision MESSAGE="migration description"`

The backend uses `uv` against `backend/pyproject.toml`. Do not substitute `pip`, Poetry, or another dependency manager.

### Frontend

* Install dependencies: `make frontend-install`
* Start the Vite development server: `make frontend-dev`
* Build the SPA into `backend/static`: `make frontend-build`
* Lint with fixes: `make frontend-lint`
* Format: `make frontend-format`
* Typecheck (`tsc`): `make frontend-typecheck`
* Test: `make frontend-test`

The frontend uses `npm`. Do not substitute another package manager.

### Database

* Start Postgres and Redis: `make up`
* Stop Postgres and Redis: `make down`
* Reset Postgres and Redis and delete their data: `make reset` (prompts for confirmation)
* Follow Postgres and Redis logs: `make logs`

Do not run `make reset` unless the task explicitly permits deleting local database and Redis data.

## Backend Architecture

### Routers

Routers should remain thin.

Routers may:

* Handle FastAPI request and response concerns.
* Declare routes, dependencies, status codes, and response schemas.
* Read path, query, header, cookie, and body values.
* Call one or more service functions.
* Coordinate multiple services at a single HTTP boundary.
* Convert service results into HTTP responses.

Routers should not:

* Contain application workflows.
* Contain database business logic.
* Perform AI extraction directly.
* Send login-code emails directly.
* Duplicate logic that belongs in a service.

### Services

Services own application behavior and workflows.

* Routers should delegate application operations to service functions.
* A service may call another service when the workflow requires it.
* Do not pass the authenticated actor into a service unless the actor is logically required by the operation itself.
* Authentication, admin protection, and rate limiting normally belong in FastAPI dependencies rather than being reproduced inside services.
* Do not couple services to FastAPI request or response objects.
* Services construct and mutate ORM entities, but delegate every session interaction to their feature's repository.

### Repositories and stores

Each feature's data access lives in a dedicated module beside its service:

* `repository.py` owns all database access for the feature: query construction and every `AsyncSession` call (`select`/`execute`/`get`/`add`/`delete`/`flush`).
* The Redis-backed auth sub-features (`sessions/`, `email_challenges/`, `oauth/`) use a `store.py` instead: it owns all Redis commands, key building, TTL enforcement, and value encoding/decoding.
* Repositories and stores are feature-private: only the owning feature's service imports them. Cross-feature access goes service to service. Within a feature namespace, a sub-feature repository may import a sibling sub-feature repository's read functions rather than duplicating the query; writes stay in the owning sub-feature's repository.
* Services never build queries, call `db.*`, or issue Redis commands directly. Background jobs may own their transaction boundary (`async with sessionmaker() as db`, commit/rollback) but perform all reads and writes through the repository.
* Flush placement is behavior (it controls when integrity errors surface for translation); preserve it when moving code.
* Crypto stays out of stores: services hash tokens and codes; stores receive hashes.

### Dependencies

FastAPI dependencies own request-bound concerns such as:

* Database session access.
* Authentication.
* Admin authorization.
* Rate limiting.
* CSRF validation.
* Access to configured external clients.

Do not move request-bound authorization checks into services merely to make a router shorter.

### Composition and external clients

* Construct database and external client resources through the application lifespan.
* Store application-wide resources on `app.state`.
* Access those resources through dependencies.
* Validate provider-conditional configuration in the settings group that owns it (`core/config/`), not in the lifespan. The selected provider's own settings are required and the other providers' are ignored, so an incomplete deployment fails to load its configuration rather than failing on first use.
* A lifespan may still guard those settings, but only to narrow an optional field for the type checker; say so where the guard lives.
* Keep provider-specific implementation details inside `integrations/`.
* Keep generic document classification and extraction behavior inside `document_ai/`.
* Keep cashout-specific extraction behavior inside the cashout feature.

## Transactions and Deferred Work

Deferred work runs through the transactional outbox (`backend/app/infrastructure/outbox/`): `enqueue` persists a message inside the caller's transaction, and dispatcher workers started by the app lifespan deliver it through the owning feature's registered handler (`features/<feature>/outbox.py`).

* AI extraction and login-code email delivery both run through the outbox.
* Do not introduce another deferred-work mechanism without explicit instruction.
* Do not send emails or start AI extraction before the required database transaction has committed.
* Keep HTTP routers unaware of the low-level delivery mechanism.
* In tests, delivery is explicit: the app fixture runs no dispatcher, so use the `drain_outbox` fixture to run enqueued work.

## Errors

Error translation is centralized in `backend/app/errors/translators.py`.

Use the existing translators:

* `translate_integrity_errors`
* `translate_validation_errors`

Do not scatter equivalent integrity-error or validation-error translation across routers and services.

* Feature code may define or raise meaningful application and domain errors.
* Preserve the shared API error contract.
* Do not expose raw database, validation-library, or provider exceptions directly through HTTP responses.
* Add translation behavior to the centralized error system when a new known exception requires normalization.

## Database Changes

Migration history is currently managed pragmatically rather than as a permanently immutable production history.

* For small schema changes, update the initial migration.
* For significant changes, such as introducing a new feature, create a new migration.
* Keep ORM models and migrations consistent.
* Inspect existing migrations before deciding whether a change belongs in the initial migration or a new revision.
* Do not generate a migration automatically when no persisted schema changed.

## Frontend

* Follow the structure and conventions of adjacent frontend code.
* Reuse the existing fetch client and shared API error handling in `frontend/src/api/`.
* Keep authentication and route protection within the existing auth provider and guards.
* Keep cashier functionality in `frontend/src/features/cashout/`.
* Keep admin functionality in `frontend/src/features/admin/`.
* Reuse shared primitives from `frontend/src/components/ui.tsx` before creating duplicate components.
* Use centralized theme tokens rather than hard-coded component colors.
* Preserve loading, empty, error, and authorization states when changing a user-facing workflow.
* Do not introduce a new state-management, routing, styling, or API-client approach without an explicit architectural reason.

## Testing

Tests required before considering a task complete:

* Backend-only task: `make backend-test`
* Frontend-only task: `make frontend-test`
* Cross-cutting backend and frontend task: `make test`

Also:

* Add or update tests when observable behavior changes.
* Prefer testing behavior over implementation details.
* Reuse existing fixtures and helpers where appropriate.
* Cover the main success path and meaningful failure paths.
* Do not delete or weaken a test merely to make a change pass.
* Report failing tests clearly when the failure is unrelated to the requested change.

## API and Data Contract Changes

When changing an API contract:

* Update backend request and response schemas.
* Update frontend typed contracts.
* Update affected API calls and consumers.
* Update relevant tests.
* Preserve the shared error response format.
* Do not silently remove or rename fields unless the task explicitly requires a breaking change.

## Security

* Never commit secrets, credentials, tokens, private keys, or production data.
* Do not weaken authentication, admin authorization, rate limiting, CSRF protection, or validation to simplify an implementation.
* Treat all request data and uploaded documents as untrusted input.
* Do not expose provider errors or sensitive internal details in API responses.
* Call out security-sensitive assumptions and behavior changes.

## Git

* Do not commit unless the user explicitly authorizes commits.
* Do not push, amend, rebase, reset, or discard changes unless explicitly requested.
* Do not modify unrelated existing work.
* Keep changes focused on the requested task.
* Review the diff before an authorized commit.
* Do not include generated or unrelated files in a commit.

## Definition of Done

A task is complete only when:

* The requested behavior is implemented.
* Routers remain limited to HTTP concerns and service orchestration.
* Application behavior resides in services or the appropriate domain component.
* Existing architectural boundaries are preserved.
* Relevant tests are added or updated.
* The required backend, frontend, or cross-cutting test command passes.
* API contracts and frontend types are updated when applicable.
* ORM and migration changes are consistent when applicable.
* Existing authentication, authorization, CSRF, and error behavior remain intact.
* No unrelated files or refactors are included.
* Remaining limitations, failed checks, or unresolved architectural decisions are stated clearly.
