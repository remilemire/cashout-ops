# backend/tests/conftest.py

from __future__ import annotations

import os

import pytest

# The throwaway Postgres is cleaned up by the fixture's `with` block, so disable
# testcontainers' Ryuk reaper (it needs a separate image that may be unavailable).
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# The app.core.config import below builds the settings singleton at import
# time from os.environ plus any developer .env. These pins keep that throwaway
# construction valid with or without a .env, whatever provider a developer's
# .env selects (e.g. STORAGE_PROVIDER=S3 without credentials would otherwise
# abort collection), without shipping any provider's credentials; os.environ
# wins over .env. Value isolation is the hermetic baseline's job, below.
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused/unused")
os.environ.setdefault("REDIS_URL", "redis://unused:6379/0")
os.environ.setdefault("AI_MODEL", "claude-sonnet-5")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("EMAIL_PROVIDER", "CONSOLE")
# Pinned as a pair: a developer .env carrying only one of the two would
# otherwise fail AuthSettings' set-together validation at import.
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
os.environ.setdefault("BOOTSTRAP_OWNER_EMAIL", "owner@test.com")
os.environ.setdefault("STORAGE_PROVIDER", "LOCAL")
os.environ.setdefault("STORAGE_LOCAL_DIR", "storage/documents")

# Replace every group on the live singleton with the hermetic baseline so no
# test observes a .env value. This must sit below the pins (they keep the
# import-time construction valid) and above pytest_plugins: the fixture
# modules import app.* feature modules, at least one of which bakes a settings
# value at import time (the cashout error catalog's DOCUMENT_TOO_LARGE
# message). Overwriting attributes preserves the singleton's identity, so
# every `from app.core.config import settings` importer sees the baseline.
from app.core.config import Settings, settings  # noqa: E402
from tests.support.settings import make_test_settings  # noqa: E402

_test_settings = make_test_settings()
for _group in Settings.model_fields:
    setattr(settings, _group, getattr(_test_settings, _group))

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
