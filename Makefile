# Makefile — repo-wide orchestration (backend + frontend + database).
# Backend targets call uv directly against backend/pyproject.toml; frontend targets use npm.

.DEFAULT_GOAL := help

UV := uv --directory backend

.PHONY: help install-uv setup install format lint test check migrate \
	build start \
	backend-install backend-dev backend-format backend-lint backend-test backend-check backend-migrate backend-revision \
	frontend-install frontend-dev frontend-build frontend-lint frontend-format frontend-test \
	db-up db-down db-logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

## ── Setup / aggregate ──────────────────────────────────────────────


install: backend-install frontend-install ## Install backend + frontend deps

format: backend-format frontend-format ## Format backend + frontend

lint: backend-lint frontend-lint ## Lint (with fixes) backend + frontend

test: backend-test frontend-test ## Test backend + frontend

check: backend-check frontend-lint frontend-test ## Format + lint + test everything

migrate: backend-migrate ## Apply database migrations

## ── Deployment (Render commands) ───────────────────────────────────

build: install frontend-build ## Render build command (deps + SPA build)

start: ## Render start command (gunicorn on $$PORT)
	$(UV) run gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$$PORT

## ── Backend (uv, against backend/pyproject.toml) ───────────────────

backend-install: ## uv sync
	$(UV) sync

backend-dev: ## Run the API with reload (fastapi dev)
	$(UV) run fastapi dev

backend-format: ## ruff format
	$(UV) run ruff format .

backend-lint: ## ruff check --fix
	$(UV) run ruff check . --fix

backend-test: ## pytest
	$(UV) run pytest

backend-check: backend-format backend-lint backend-test ## Backend format + lint + test

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

frontend-format: ## prettier --write
	cd frontend && npm run format

frontend-test: ## vitest
	cd frontend && npm run test

## ── Database (docker compose) ──────────────────────────────────────

db-up: ## Start Postgres (detached)
	docker compose up -d

db-down: ## Stop Postgres
	docker compose down

db-logs: ## Tail Postgres logs
	docker compose logs -f db
