"""Exercise the squashed migration against an empty Postgres database.

Most tests create the application schema directly from ORM metadata. These
checks cover the deployment path instead, including the reporting objects that
are intentionally outside that metadata.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.infrastructure.db import registry

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRATCH_DB = "migrations_test"


@pytest.fixture
def migrated_url(postgres_url: str) -> Iterator[str]:
    """Create an empty database on the test Postgres server."""
    url = make_url(postgres_url)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    try:
        yield url.set(database=SCRATCH_DB).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _alembic(url: str, *args: str) -> None:
    # Keep env.py's dotenv and logging setup isolated from the test process.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _enum_values(url: str, name: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e"
                    " JOIN pg_type t ON t.oid = e.enumtypid"
                    " WHERE t.typname = :name"
                ),
                {"name": name},
            )
            return {row[0] for row in rows}
    finally:
        engine.dispose()


def test_initial_migration_matches_current_models(migrated_url: str) -> None:
    _alembic(migrated_url, "upgrade", "head")

    engine = create_engine(migrated_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            *registry.metadata.tables,
            "alembic_version",
        }

        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == "1e3b9a4fbf7d"
            )

        assert _enum_values(migrated_url, "tipout_department") == {
            "bar",
            "kitchen",
            "expo",
            "host",
            "manager",
        }
        assert _enum_values(migrated_url, "cashout_document_classification") == {
            "touchbistro_report",
            "server_summary_report",
            "gift_certificate",
        }

        # Alembic compares the migrated database back to the ORM metadata and
        # fails if autogenerate would produce any table-schema changes.
        _alembic(migrated_url, "check")
    finally:
        engine.dispose()


def test_initial_migration_creates_reporting_surface(migrated_url: str) -> None:
    _alembic(migrated_url, "upgrade", "head")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111',
                            'Cashier', 'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111',
                            now(), '2026-09-11');
                    INSERT INTO cashout_data
                        (id, submission_id, food_net_sales, drink_net_sales,
                         total_net_sales, card_payment_total,
                         cash_payment_total, card_tip_total,
                         tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate,
                         host_tipout_rate, manager_tipout_rate)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            800.00, 400.00, 1200.00, 1234.56, 150.00, 180.00,
                            ARRAY['kitchen', 'manager']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100, 0.0100);
                    """
                )
            )

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT display_order, employee_name, business_date,"
                    " kitchen_tipout, bar_tipout, expo_tipout, host_tipout,"
                    " cash_owed_to_house, cash_owed_to_employee"
                    " FROM reporting.cashout_data"
                )
            ).one()
            view_columns = [
                value
                for (value,) in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_schema = 'reporting'"
                        " AND table_name = 'cashout_data'"
                        " ORDER BY ordinal_position"
                    )
                )
            ]

        assert row == (1, "Cashier", "2026-09-11", 24.0, None, None, None, 6.0, None)
        assert view_columns[:9] == [
            "employee_name",
            "business_date",
            "kitchen_tipout",
            "bar_tipout",
            "expo_tipout",
            "host_tipout",
            "cash_owed_to_house",
            "cash_owed_to_employee",
            "display_order",
        ]
        assert view_columns[-2:] == ["deposit_total", "adjustment_note"]
    finally:
        engine.dispose()

    reader = create_engine(migrated_url, isolation_level="AUTOCOMMIT")
    try:
        with reader.connect() as conn:
            conn.execute(text("SET ROLE reporting_reader"))
            assert (
                conn.execute(
                    text("SELECT count(*) FROM reporting.cashout_data")
                ).scalar_one()
                == 1
            )
            with pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(text("SELECT * FROM public.cashout_data"))
    finally:
        reader.dispose()


def test_initial_migration_downgrades_and_reupgrades(migrated_url: str) -> None:
    _alembic(migrated_url, "upgrade", "head")
    _alembic(migrated_url, "downgrade", "base")

    engine = create_engine(migrated_url)
    try:
        inspector = inspect(engine)
        assert inspector.get_table_names() == ["alembic_version"]
        assert inspector.get_view_names(schema="reporting") == []
        assert _enum_values(migrated_url, "tipout_department") == set()

        # The group role is cluster-wide and may have login-role memberships,
        # so downgrade removes its database objects and grants but keeps it.
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_roles"
                        " WHERE rolname = 'reporting_reader'"
                    )
                ).scalar_one()
                == 1
            )

        _alembic(migrated_url, "upgrade", "head")
        _alembic(migrated_url, "check")
    finally:
        engine.dispose()
