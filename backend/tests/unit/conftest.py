# backend/tests/unit/conftest.py

"""Guards enforcing the unit-tier contract: no database, no Docker, no app.

These shadow the real fixtures so any unit test that (transitively) reaches
for the database or the HTTP stack fails loudly instead of silently starting
a Postgres container. Everything DB-shaped flows through `postgres_url`;
everything HTTP-shaped flows through `app` — two guards cover the graph.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

_MSG = (
    "unit tests must not touch the database or the app; "
    "use tests/support fakes, or move this test to tests/integration"
)


@pytest.fixture(scope="session")
def postgres_url() -> str:
    raise RuntimeError(_MSG)


@pytest.fixture
def app() -> FastAPI:
    raise RuntimeError(_MSG)
