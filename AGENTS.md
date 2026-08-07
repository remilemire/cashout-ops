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
* `backend/app/core/` contains configuration, cookies, and shared schemas.
* `backend/app/infrastructure/` contains low-level infrastructure such as the database foundations (`db/`: Base, registry) and the Redis client (`redis/`: the `Redis` type and its lifespan).
* `backend/app/lib/` contains pure helpers such as casing and document utilities.
* `backend/app/security/` contains password hashing, session and CSRF cookie helpers, and secret-token cryptography.
* `backend/app/dependencies/` contains FastAPI dependencies for the database, authentication, CSRF, and clients.
* `backend/app/errors/` contains domain errors, handlers, translators, and OpenAPI error shapes.
* `backend/app/integrations/` contains external AI and storage clients.
* `backend/app/documents/` contains generic document classification and extraction behavior.
* `backend/app/features/` contains feature modules such as auth (with its `sessions/` and `email_verification/` submodules), users, invitations, and cashout.
* `backend/app/features/cashout/extraction/` contains cashout-specific document processing, extraction schemas, and processor registration.
* `backend/app/api/__init__.py` mounts feature routers under `/api`.
* `frontend/src/api/` contains the fetch client, CSRF handling, the shared error contract, and typed API contracts.
* `frontend/src/auth/` contains authentication state, guards, login, registration, and email-verification gating.
* `frontend/src/features/cashout/` contains the cashier submission workflow.
* `frontend/src/features/admin/` contains admin submission and data-table workflows.
* `frontend/src/components/ui.tsx` contains shared UI primitives.
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

* Start Postgres and Redis: `make db-up`
* Stop Postgres and Redis: `make db-down`
* Reset Postgres and Redis and delete their data: `make db-reset`
* Follow Postgres logs: `make db-logs`

Do not run `make db-reset` unless the task explicitly permits deleting local database and Redis data.

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
* Send verification emails directly.
* Duplicate logic that belongs in a service.

### Services

Services own application behavior and workflows.

* Routers should delegate application operations to service functions.
* A service may call another service when the workflow requires it.
* Do not pass the authenticated actor into a service unless the actor is logically required by the operation itself.
* Authentication, admin protection, and verified-user enforcement normally belong in FastAPI dependencies rather than being reproduced inside services.
* Do not couple services to FastAPI request or response objects.

### Dependencies

FastAPI dependencies own request-bound concerns such as:

* Database session access.
* Authentication.
* Admin authorization.
* Verified-user enforcement.
* CSRF validation.
* Access to configured external clients.

Do not move request-bound authorization checks into services merely to make a router shorter.

### Composition and external clients

* Construct database and external client resources through the application lifespan.
* Store application-wide resources on `app.state`.
* Access those resources through dependencies.
* Keep provider-specific implementation details inside `integrations/`.
* Keep generic document classification and extraction behavior inside `documents/`.
* Keep cashout-specific extraction behavior inside the cashout feature.

## Transactions and Deferred Work

Post-commit tasks are currently used for:

* AI extraction.
* Verification email delivery.

The planned replacement is a transactional outbox.

* Do not introduce a second deferred-work mechanism without explicit instruction.
* Do not send emails or start AI extraction before the required database transaction has committed.
* When implementing the transactional outbox task, replace the applicable post-commit behavior rather than layering an unrelated mechanism beside it.
* Keep HTTP routers unaware of the low-level delivery mechanism.

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
* Keep authentication and route protection within the existing auth provider, guards, and verification gate.
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
* Do not weaken authentication, admin authorization, email-verification enforcement, CSRF protection, or validation to simplify an implementation.
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
