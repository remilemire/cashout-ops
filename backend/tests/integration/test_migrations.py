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
from sqlalchemy.exc import ProgrammingError

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


def _alembic(url: str, *args: str) -> None:
    # A subprocess, not the alembic API: env.py calls load_dotenv() and
    # reconfigures logging, neither of which may leak into this process (the
    # hermetic settings tests depend on the environment staying untouched).
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _upgrade(url: str, revision: str) -> None:
    _alembic(url, "upgrade", revision)


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


def _analysis_nullability(url: str) -> dict[str, bool]:
    engine = create_engine(url)
    try:
        columns = inspect(engine).get_columns("cashout_document_analyses")
        return {c["name"]: bool(c["nullable"]) for c in columns}
    finally:
        engine.dispose()


def _data_nullability(url: str) -> dict[str, bool]:
    engine = create_engine(url)
    try:
        columns = inspect(engine).get_columns("cashout_data")
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


def test_upgrade_head_fails_unknown_classifications(migrated_url: str) -> None:
    """`unknown` leaves the enum, and the analyses holding it become failures.

    An unplaceable document is a failed extraction now, not a classification:
    a database carrying the old value must come out of `upgrade head` with
    those analyses in the state a fresh extraction would produce.
    """
    _upgrade(migrated_url, "f6c0323b07d2")
    assert "unknown" in _enum_values(migrated_url, "cashout_document_classification")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_documents
                        (id, cashout_submission_id, content_type, storage_key,
                         original_filename, checksum_sha256, uploaded_by_user_id,
                         uploaded_at)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            'application/pdf', 'key', 'doc.pdf', 'checksum',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_document_analyses
                        (id, cashout_document_id, provider, model, status,
                         classification, classification_confidence, completed_at)
                    VALUES ('44444444-4444-4444-4444-444444444444',
                            '33333333-3333-3333-3333-333333333333', 'anthropic',
                            'some-model', 'needs_verification', 'unknown', 0.3,
                            now());
                    """
                )
            )

        _upgrade(migrated_url, "head")

        assert _enum_values(migrated_url, "cashout_document_classification") == {
            "touchbistro_report",
            "server_summary_report",
        }
        with engine.connect() as conn:
            status, classification, error_code, error_message = conn.execute(
                text(
                    "SELECT status, classification, error_code, error_message"
                    " FROM cashout_document_analyses"
                )
            ).one()
        assert status == "failed"
        assert classification is None
        assert error_code == "unclassifiable_document"
        assert error_message
    finally:
        engine.dispose()


def test_upgrade_head_reopens_unreconciled_cashouts(migrated_url: str) -> None:
    """The source figures become NOT NULL, and figure-less rows go with it.

    A cashout completed before reconciliation carries no figures, and there
    is nothing in SQL to fill them from — so `upgrade head` reopens it the
    way unsubmit does: the row is dropped, the submission returns to
    PROCESSING with its analyses still verified, and completing it once more
    reconciles it properly.
    """
    _upgrade(migrated_url, "4c8f21d0a7b3")
    assert _data_nullability(migrated_url)["food_net_sales"] is True

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, status,
                         completed_by_user_id, first_completed_at,
                         tipout_departments)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            'completed',
                            '11111111-1111-1111-1111-111111111111', now(),
                            ARRAY['kitchen']::tipout_department[]);
                    INSERT INTO cashout_data
                        (id, submission_id, tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate, host_tipout_rate)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '22222222-2222-2222-2222-222222222222',
                            ARRAY['kitchen']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100);
                    """
                )
            )

        _upgrade(migrated_url, "head")

        assert _data_nullability(migrated_url)["food_net_sales"] is False
        with engine.connect() as conn:
            assert (
                conn.execute(text("SELECT count(*) FROM cashout_data")).scalar_one()
                == 0
            )
            status, completed_by, first_completed_at, departments = conn.execute(
                text(
                    "SELECT status, completed_by_user_id, first_completed_at,"
                    " array_to_string(tipout_departments, ',')"
                    " FROM cashout_submissions"
                )
            ).one()
        # Reopened, not erased: the completion on record and the tipout choice
        # survive, exactly as they do through an unsubmit.
        assert status == "processing"
        assert completed_by is None
        assert first_completed_at is not None
        assert departments == "kitchen"
    finally:
        engine.dispose()


def test_upgrade_head_recalculates_cash_balance_with_tipouts(
    migrated_url: str,
) -> None:
    """Existing reconciled rows adopt the tipout-aware cash balance."""
    _upgrade(migrated_url, "d2b8a4e91c05")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            # The initial migration is kept current for fresh installs, so
            # recreate the generated expressions an already-applied database
            # has immediately before this new revision reaches it.
            conn.execute(
                text(
                    """
                    ALTER TABLE cashout_data
                        DROP COLUMN cash_owed_to_house,
                        DROP COLUMN cash_owed_to_employee;
                    ALTER TABLE cashout_data ADD COLUMN cash_owed_to_house
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE
                                WHEN cash_payment_total > card_tip_total
                                THEN cash_payment_total - card_tip_total
                                ELSE NULL
                            END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN cash_owed_to_employee
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE
                                WHEN card_tip_total > cash_payment_total
                                THEN card_tip_total - cash_payment_total
                                ELSE NULL
                            END
                        ) STORED;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-09-01');
                    INSERT INTO cashout_data
                        (id, submission_id, food_net_sales, drink_net_sales,
                         total_net_sales, card_payment_total,
                         cash_payment_total, card_tip_total,
                         tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate,
                         host_tipout_rate)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '22222222-2222-2222-2222-222222222222',
                            800.00, 400.00, 1200.00, 1234.56, 150.00, 180.00,
                            ARRAY['kitchen', 'bar']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100);
                    """
                )
            )

        with engine.connect() as conn:
            before = conn.execute(
                text(
                    "SELECT cash_owed_to_house, cash_owed_to_employee FROM cashout_data"
                )
            ).one()
        assert before == (None, 30)

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            after = conn.execute(
                text(
                    "SELECT cash_owed_to_house, cash_owed_to_employee FROM cashout_data"
                )
            ).one()
        # The 20.00 bar and 24.00 kitchen tipouts turn a 30.00 employee
        # receivable into 14.00 owed to the house.
        assert after == (14, None)
    finally:
        engine.dispose()


def test_upgrade_head_recalculates_cashouts_with_house_favouring_rounding(
    migrated_url: str,
) -> None:
    """Existing rows adopt per-department ceiling rather than nearest-cent."""
    _upgrade(migrated_url, "a34f9c2d71be")

    old_total_tipout = """
        CASE WHEN 'bar'::tipout_department = ANY(tipout_departments)
            THEN drink_net_sales * bar_tipout_rate ELSE 0 END
        + CASE WHEN 'kitchen'::tipout_department = ANY(tipout_departments)
            THEN food_net_sales * kitchen_tipout_rate ELSE 0 END
        + CASE WHEN 'expo'::tipout_department = ANY(tipout_departments)
            THEN total_net_sales * expo_tipout_rate ELSE 0 END
        + CASE WHEN 'host'::tipout_department = ANY(tipout_departments)
            THEN total_net_sales * host_tipout_rate ELSE 0 END
    """

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            # The initial migration is kept current for fresh installs. Put
            # all six generated expressions back into the exact state an
            # already-applied database has before the new revision reaches it.
            conn.execute(
                text(
                    f"""
                    ALTER TABLE cashout_data
                        DROP COLUMN cash_owed_to_employee,
                        DROP COLUMN cash_owed_to_house,
                        DROP COLUMN host_tipout,
                        DROP COLUMN expo_tipout,
                        DROP COLUMN kitchen_tipout,
                        DROP COLUMN bar_tipout;
                    ALTER TABLE cashout_data ADD COLUMN bar_tipout
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE WHEN 'bar'::tipout_department
                                = ANY(tipout_departments)
                            THEN drink_net_sales * bar_tipout_rate ELSE NULL END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN kitchen_tipout
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE WHEN 'kitchen'::tipout_department
                                = ANY(tipout_departments)
                            THEN food_net_sales * kitchen_tipout_rate ELSE NULL END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN expo_tipout
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE WHEN 'expo'::tipout_department
                                = ANY(tipout_departments)
                            THEN total_net_sales * expo_tipout_rate ELSE NULL END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN host_tipout
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE WHEN 'host'::tipout_department
                                = ANY(tipout_departments)
                            THEN total_net_sales * host_tipout_rate ELSE NULL END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN cash_owed_to_house
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE
                                WHEN cash_payment_total - card_tip_total
                                    + ({old_total_tipout}) > 0
                                THEN cash_payment_total - card_tip_total
                                    + ({old_total_tipout})
                                ELSE NULL
                            END
                        ) STORED;
                    ALTER TABLE cashout_data ADD COLUMN cash_owed_to_employee
                        numeric(12, 2) GENERATED ALWAYS AS (
                            CASE
                                WHEN cash_payment_total - card_tip_total
                                    + ({old_total_tipout}) < 0
                                THEN -(cash_payment_total - card_tip_total
                                    + ({old_total_tipout}))
                                ELSE NULL
                            END
                        ) STORED;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-09-01');
                    INSERT INTO cashout_data
                        (id, submission_id, food_net_sales, drink_net_sales,
                         total_net_sales, card_payment_total,
                         cash_payment_total, card_tip_total,
                         tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate,
                         host_tipout_rate)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '22222222-2222-2222-2222-222222222222',
                            800.01, 100.01, 1200.00, 1234.56, 150.00, 180.00,
                            ARRAY['bar', 'kitchen']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100);
                    """
                )
            )

        def generated_values() -> tuple[str | None, ...]:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT bar_tipout, kitchen_tipout, cash_owed_to_house,"
                        " cash_owed_to_employee FROM cashout_data"
                    )
                ).one()
            return tuple(None if value is None else str(value) for value in row)

        assert generated_values() == ("5.00", "24.00", None, "1.00")

        _upgrade(migrated_url, "head")

        assert generated_values() == ("5.01", "24.01", None, "0.98")
    finally:
        engine.dispose()


def test_upgrade_head_dedups_live_cashout_days(migrated_url: str) -> None:
    """Same-day live duplicates are soft-deleted before the day becomes unique.

    The business_date backfill gave same-day submissions the same date, so a
    database can hold several live cashouts for one (employee, day) — which
    the new partial unique index cannot be created over. `upgrade head` keeps
    the best row per day (a completed cashout outranks drafts, then the
    newest) and soft-deletes the rest, exactly as cancelling does.
    """
    _upgrade(migrated_url, "c7a4e29d81b3")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date,
                         status)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111',
                            now() - interval '1 hour', '2026-08-28',
                            'completed'),
                           ('33333333-3333-3333-3333-333333333333',
                            '11111111-1111-1111-1111-111111111111',
                            now(), '2026-08-28', 'processing');
                    """
                )
            )

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            live_by_id = {
                row[0]: row[1]
                for row in conn.execute(
                    text("SELECT id::text, deleted_at IS NULL FROM cashout_submissions")
                )
            }
            indexdef = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname ="
                    " 'ix_cashout_submissions_employee_business_date'"
                )
            ).scalar_one()
        # The completed cashout keeps the day even though the draft is newer:
        # it holds the day's reconciled data, and the app refuses to delete
        # it. The draft is soft-deleted, not removed.
        assert live_by_id == {
            "22222222-2222-2222-2222-222222222222": True,
            "33333333-3333-3333-3333-333333333333": False,
        }
        # The index the dedup made room for: unique over live rows only.
        assert "UNIQUE" in indexdef
        assert "deleted_at IS NULL" in indexdef
    finally:
        engine.dispose()


def test_upgrade_head_stamps_existing_extractions_at_version_one(
    migrated_url: str,
) -> None:
    """Pre-versioning extraction data is backfilled as schema version 1.

    Every row written before versions were recorded came from a version-1
    schema — the only version that has existed — so `upgrade head` stamps the
    rows that hold data. Rows with no schema captured (failed or in-flight
    analyses) stay null, like their schema_name.
    """
    # The last revision before schema versions were recorded.
    _upgrade(migrated_url, "e8f4a2b19c67")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-08-28');
                    INSERT INTO cashout_documents
                        (id, cashout_submission_id, content_type, storage_key,
                         original_filename, checksum_sha256, uploaded_by_user_id,
                         uploaded_at)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            'application/pdf', 'key-1', 'doc.pdf', 'checksum-1',
                            '11111111-1111-1111-1111-111111111111', now()),
                           ('44444444-4444-4444-4444-444444444444',
                            '22222222-2222-2222-2222-222222222222',
                            'application/pdf', 'key-2', 'other.pdf',
                            'checksum-2',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_document_analyses
                        (id, cashout_document_id, provider, model, status,
                         classification, schema_name, extracted_data_json,
                         completed_at)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '33333333-3333-3333-3333-333333333333', 'anthropic',
                            'some-model', 'needs_verification',
                            'server_summary_report', 'ServerSummaryReportData',
                            '{"grand_total": "1.00"}'::jsonb, now()),
                           ('66666666-6666-6666-6666-666666666666',
                            '44444444-4444-4444-4444-444444444444', 'anthropic',
                            'some-model', 'failed', NULL, NULL, NULL, now());
                    """
                )
            )

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            version_by_id = {
                row[0]: row[1]
                for row in conn.execute(
                    text(
                        "SELECT id::text, schema_version FROM cashout_document_analyses"
                    )
                )
            }
        assert version_by_id == {
            "55555555-5555-5555-5555-555555555555": 1,
            "66666666-6666-6666-6666-666666666666": None,
        }
    finally:
        engine.dispose()


def test_upgrade_head_creates_reporting_view(migrated_url: str) -> None:
    """`upgrade head` publishes the reconciled cashouts to the reporting view.

    `reporting.cashout_data` mirrors the admin "Cashout data" table for the
    management Google Sheet, whose login role reads it as a member of
    `reporting_reader` — a role that sees the view and nothing else.
    """
    # The last revision before the reporting view.
    _upgrade(migrated_url, "9d3e5f81a2c4")

    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, full_name, email)
                    VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                            'cashier@test.com');
                    INSERT INTO cashout_submissions
                        (id, employee_user_id, submitted_at, business_date)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-08-10');
                    INSERT INTO cashout_data
                        (id, submission_id, food_net_sales, drink_net_sales,
                         total_net_sales, card_payment_total,
                         cash_payment_total, card_tip_total,
                         tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate,
                         host_tipout_rate)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '22222222-2222-2222-2222-222222222222',
                            800.00, 400.00, 1200.00, 1234.56, 150.00, 180.00,
                            ARRAY['kitchen']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100);
                    """
                )
            )

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT display_order, employee_name, business_date,"
                    " kitchen_tipout, bar_tipout, expo_tipout, host_tipout,"
                    " cash_owed_to_house, cash_owed_to_employee"
                    " FROM reporting.cashout_data"
                )
            ).one()
        # The sheet's nine columns, by position. The 24.00 kitchen tipout
        # (3% of 800.00 food) turns the 30.00 cash shortfall into 6.00 owed
        # to the employee; the business day is the API's ISO text, not a
        # date, and the money is numbers, not numeric-as-text.
        assert row == (1, "Cashier", "2026-08-10", 24.0, None, None, None, None, 6.0)
    finally:
        engine.dispose()

    # AUTOCOMMIT: the denied statement must not abort a transaction the
    # other assertions share.
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


def test_reporting_view_survives_downgrade_and_reupgrade(
    migrated_url: str,
) -> None:
    """Downgrading removes the view but keeps the role; upgrading again
    rebuilds the view and its grant around that existing role.

    The role is cluster-wide and carries the sheet's login role as a member,
    so it must outlive the schema — and the upgrade must cope with finding it
    already there.
    """
    _upgrade(migrated_url, "head")
    _alembic(migrated_url, "downgrade", "9d3e5f81a2c4")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT count(*) FROM pg_views WHERE schemaname = 'reporting'")
                ).scalar_one()
                == 0
            )
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_roles WHERE rolname = 'reporting_reader'"
                    )
                ).scalar_one()
                == 1
            )

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_views"
                        " WHERE schemaname = 'reporting' AND viewname = 'cashout_data'"
                    )
                ).scalar_one()
                == 1
            )
            assert (
                conn.execute(
                    text(
                        "SELECT has_table_privilege('reporting_reader',"
                        " 'reporting.cashout_data', 'SELECT')"
                    )
                ).scalar_one()
                is True
            )
    finally:
        engine.dispose()
