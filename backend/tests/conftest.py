# backend/tests/conftest.py

from __future__ import annotations

import os

import pytest

# The throwaway Postgres is cleaned up by the fixture's `with` block, so disable
# testcontainers' Ryuk reaper (it needs a separate image that may be unavailable).
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Required settings must exist before anything imports app.core.config. Set them
# here so the suite runs without a .env (e.g. in CI); os.environ wins over .env.
# This block must stay above pytest_plugins: the fixture modules import app.*.
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused/unused")
os.environ.setdefault("REDIS_URL", "redis://unused:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("BOOTSTRAP_OWNER_EMAIL", "owner@test.com")
os.environ.setdefault("STORAGE_LOCAL_DIR", "storage/documents")

pytest_plugins = [
    "tests.support.fixtures.db",
    "tests.support.fixtures.redis",
    "tests.support.fixtures.integrations",
    "tests.support.fixtures.app",
    "tests.support.fixtures.clients",
    "tests.support.fixtures.outbox",
]


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Mark tests by tier directory so `-m unit` / `-m integration` work."""
    for item in items:
        try:
            parts = item.path.relative_to(config.rootpath).parts
        except ValueError:
            continue
        if parts[:2] == ("tests", "unit"):
            item.add_marker(pytest.mark.unit)
        elif parts[:2] == ("tests", "integration"):
            item.add_marker(pytest.mark.integration)
