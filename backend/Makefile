# backend/Makefile

.PHONY: format lint test check revision migrate install

install:
	uv sync

format:
	uv run ruff format .

lint:
	uv run ruff check . --fix

test:
	uv run pytest

check: format lint test

MESSAGE ?= migration
revision:
	uv run alembic revision --autogenerate -m "$(MESSAGE)"

migrate:
	uv run alembic upgrade head

run:
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload