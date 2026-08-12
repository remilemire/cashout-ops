# Makefile — repo-wide orchestration (backend + frontend + database).
# Backend targets call uv directly against backend/pyproject.toml; frontend targets use npm.

.DEFAULT_GOAL := help

UV := uv --directory backend
DOCKER_DATABASE_URL := postgresql+psycopg://postgres:dev@localhost:5432/cashout_ops

.PHONY: help install-uv setup install format lint typecheck test check migrate \
	build start \
	backend-install backend-dev backend-format backend-lint backend-typecheck backend-test backend-test-unit backend-test-integration backend-check backend-migrate backend-revision \
	frontend-install frontend-dev frontend-build frontend-lint frontend-typecheck frontend-format frontend-test \
	up down reset logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

## ── Setup / aggregate ──────────────────────────────────────────────


install: backend-install frontend-install ## Install backend + frontend deps

format: backend-format frontend-format ## Format backend + frontend

lint: backend-lint frontend-lint ## Lint (with fixes) backend + frontend

test: backend-test frontend-test ## Test backend + frontend

typecheck: backend-typecheck frontend-typecheck ## Typecheck backend + frontend

check: backend-check frontend-lint frontend-typecheck frontend-test ## Format + lint + typecheck + test everything

migrate: backend-migrate ## Apply database migrations

## ── Deployment (Render commands) ───────────────────────────────────

build: install frontend-build ## Render build command (deps + SPA build)

# Behind Render only the platform proxy can reach the service, so trusting
# X-Forwarded-For from any peer is safe there; uvicorn's worker then rewrites
# request.client to the real client for per-IP rate limiting.
start: ## Render start command (gunicorn on $$PORT)
	$(UV) run gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$$PORT --forwarded-allow-ips='*'

## ── Backend (uv, against backend/pyproject.toml) ───────────────────

backend-install: ## uv sync
	$(UV) sync

backend-dev: ## Run the API with reload (fastapi dev)
	$(UV) run fastapi dev

backend-format: ## ruff format
	$(UV) run ruff format .

backend-lint: ## ruff check --fix
	$(UV) run ruff check . --fix

backend-typecheck: ## pyright (strict)
	$(UV) run pyright

backend-test: ## pytest
	$(UV) run pytest

backend-test-unit: ## pytest tests/unit (fast; no Docker/Postgres)
	$(UV) run pytest tests/unit

backend-test-integration: ## pytest tests/integration (real Postgres via testcontainers)
	$(UV) run pytest tests/integration

backend-check: backend-format backend-lint backend-typecheck backend-test ## Backend format + lint + typecheck + test

backend-migrate: ## alembic upgrade head
	$(UV) run alembic upgrade head

MESSAGE ?= migration
backend-revision: ## Autogenerate a migration (MESSAGE="…")
	$(UV) run alembic revision --autogenerate -m "$(MESSAGE)"

## ── Frontend (npm) ─────────────────────────────────────────────────

frontend-install: ## npm ci
	cd frontend && npm ci

frontend-dev: ## Vite dev server
	cd frontend && npm run dev

frontend-build: ## Build SPA into backend/static
	cd frontend && npm run build

frontend-lint: ## eslint --fix
	cd frontend && npm run lint

frontend-typecheck: ## tsc --noEmit
	cd frontend && npm run typecheck

frontend-format: ## prettier --write
	cd frontend && npm run format

frontend-test: ## vitest
	cd frontend && npm run test

## ── Docker (Postgres + Redis) ───────────────────────────────────────

up: ## Start Postgres + Redis (detached)
	docker compose up -d

down: ## Stop Postgres + Redis
	docker compose down

reset: ## Delete Postgres + Redis data and restart (asks for confirmation)
	@read -p "This deletes all local Postgres and Redis data. Continue? [y/N] " ans; \
	if [ "$$ans" != "y" ] && [ "$$ans" != "Y" ]; then \
		echo "Aborted."; \
		exit 1; \
	fi
	docker compose down --volumes
	docker compose up -d

logs: ## Tail Postgres + Redis logs
	docker compose logs -f
