# backend/tests/integration/test_migrations.py
#
# The application schema in tests comes from the ORM metadata (create_all),
# so nothing else exercises the migration chain. This runs the real chain
# against a scratch database — the path an existing deployment takes.

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]

SCRATCH_DB = "migrations_test"


@pytest.fixture
def migrated_url(postgres_url: str) -> Iterator[str]:
    """A scratch database on the test server, dropped afterwards.

    Separate from the fixture database so the migration chain runs against
    empty ground rather than the create_all schema.
    """
    url = make_url(postgres_url)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    try:
        # str(URL) masks the password; render it usable for real connections.
        yield url.set(database=SCRATCH_DB).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _upgrade(url: str, revision: str) -> None:
    # A subprocess, not the alembic API: env.py calls load_dotenv() and
    # reconfigures logging, neither of which may leak into this process (the
    # hermetic settings tests depend on the environment staying untouched).
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _analysis_nullability(url: str) -> dict[str, bool]:
    engine = create_engine(url)
    try:
        columns = inspect(engine).get_columns("cashout_document_analyses")
        return {c["name"]: bool(c["nullable"]) for c in columns}
    finally:
        engine.dispose()


def test_upgrade_head_allows_manual_analyses(migrated_url: str) -> None:
    """A database on the original schema is healed by `alembic upgrade head`.

    Regression test: the nullable provider/model change first shipped as an
    edit to the already-applied initial migration, which existing databases
    never picked up — manual document entry then failed on their stale NOT
    NULL columns. The change must reach them as its own revision.
    """
    # The original schema, exactly as long-lived databases ran it.
    _upgrade(migrated_url, "f6c0323b07d2")
    before = _analysis_nullability(migrated_url)
    assert before["provider"] is False
    assert before["model"] is False

    # Upgrading to head is what heals such a database in place.
    _upgrade(migrated_url, "head")
    after = _analysis_nullability(migrated_url)
    assert after["provider"] is True
    assert after["model"] is True
