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
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError

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
            "gift_certificate",
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
        # survive, exactly as they do through an unsubmit. The choice gains the
        # manager on the way, as every snapshot does (b8e1d47c5a92).
        assert status == "processing"
        assert completed_by is None
        assert first_completed_at is not None
        assert departments == "kitchen,manager"
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
            # The initial migration is kept current for fresh installs (up to
            # the changes that later revisions can re-apply), so recreate the
            # generated expressions an already-applied database has
            # immediately before this new revision reaches it.
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
        # The 20.00 bar and 24.00 kitchen tipouts — and, since b8e1d47c5a92,
        # the 12.00 manager tipout on every cashout — turn a 30.00 employee
        # receivable into 26.00 owed to the house.
        assert after == (26, None)
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
            # The initial migration is kept current for fresh installs (up to
            # the changes that later revisions can re-apply). Put all six
            # generated expressions back into the exact state an already-applied
            # database has before the new revision reaches it.
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

        # Per-line rounding (5.01 + 24.01), plus the 12.00 manager tipout that
        # b8e1d47c5a92 adds to every cashout: 11.02 due to the house.
        assert generated_values() == ("5.01", "24.01", "11.02", None)
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
        # (3% of 800.00 food) and the 12.00 manager tipout every cashout
        # carries turn the 30.00 cash shortfall into 6.00 owed to the house;
        # the business day is the API's ISO text, not a date, and the money is
        # numbers, not numeric-as-text.
        assert row == (1, "Cashier", "2026-08-10", 24.0, None, None, None, 6.0, None)
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


def test_upgrade_head_adds_the_manager_department(migrated_url: str) -> None:
    """Existing cashouts gain the manager tipout and expo moves to food sales.

    `manager` joins the department enum and every department list (data rows
    and last-completion snapshots alike), the rate column is backfilled at 1%
    with no default left behind, the generated columns are recalculated, and
    the reporting view grows two appended columns without moving the sheet's
    nine.
    """
    # The last revision before the manager department.
    _upgrade(migrated_url, "9b2f6e1d4a73")

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
                         tipout_departments)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-09-01', ARRAY['expo']::tipout_department[]);
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
                            ARRAY['expo']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100);
                    """
                )
            )

        def as_strings(row: tuple[object, ...]) -> tuple[str | None, ...]:
            return tuple(None if value is None else str(value) for value in row)

        with engine.connect() as conn:
            before = conn.execute(
                text(
                    "SELECT expo_tipout, cash_owed_to_house, cash_owed_to_employee"
                    " FROM cashout_data"
                )
            ).one()
        # Expo on the 1200.00 total: 12.00, leaving 18.00 owed to the employee.
        assert as_strings(tuple(before)) == ("12.00", None, "18.00")

        _upgrade(migrated_url, "head")

        assert _enum_values(migrated_url, "tipout_department") == {
            "bar",
            "kitchen",
            "expo",
            "host",
            "manager",
        }
        nullability = _data_nullability(migrated_url)
        assert nullability["manager_tipout_rate"] is False
        assert nullability["manager_tipout"] is True

        with engine.connect() as conn:
            after = conn.execute(
                text(
                    "SELECT array_to_string(tipout_departments, ','),"
                    " expo_tipout, manager_tipout, manager_tipout_rate,"
                    " cash_owed_to_house, cash_owed_to_employee"
                    " FROM cashout_data"
                )
            ).one()
            snapshot = conn.execute(
                text(
                    "SELECT array_to_string(tipout_departments, ',')"
                    " FROM cashout_submissions"
                )
            ).scalar_one()
            # table_schema matters: the reporting view is also a `cashout_data`
            # with a `manager_tipout_rate` column.
            rate_default = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns"
                    " WHERE table_schema = 'public'"
                    " AND table_name = 'cashout_data'"
                    " AND column_name = 'manager_tipout_rate'"
                )
            ).scalar_one()
            view_columns = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_schema = 'reporting'"
                        " AND table_name = 'cashout_data'"
                        " ORDER BY ordinal_position"
                    )
                )
            ]
        # Expo on the 800.00 of food: 8.00. The manager, appended to the list
        # and backfilled at 1%, adds 12.00; 10.00 stays owed to the employee.
        assert as_strings(tuple(after)) == (
            "expo,manager",
            "8.00",
            "12.00",
            "0.0100",
            None,
            "10.00",
        )
        assert snapshot == "expo,manager"
        # The 1% default only backfilled the existing rows; the application
        # supplies the rate on every row it writes.
        assert rate_default is None
        # The sheet's nine columns stay where they were; the manager's two
        # are appended after them, side by side (later revisions append
        # their own columns after these, so they need not be the last).
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
        manager_at = view_columns.index("manager_tipout")
        assert manager_at >= 9
        assert view_columns[manager_at + 1] == "manager_tipout_rate"
    finally:
        engine.dispose()


def test_upgrade_head_adds_the_optional_analysis_crop(migrated_url: str) -> None:
    """Analyses gain the columns for the crop they read; earlier rows stay
    uncropped.

    An analysis from before cropping read its document whole, which is a
    state the application handles anyway (a PDF, a photo with no detectable
    text): the new columns are nullable and the backfill is simply null, so
    such an analysis keeps serving no crop until a re-extraction makes one.
    """
    # The last revision before analyses could record a crop.
    _upgrade(migrated_url, "b8e1d47c5a92")

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
                            '2026-09-01');
                    INSERT INTO cashout_documents
                        (id, cashout_submission_id, content_type, storage_key,
                         original_filename, checksum_sha256, uploaded_by_user_id,
                         uploaded_at)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            'image/jpeg', 'key', 'photo.jpg', 'checksum',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_document_analyses
                        (id, cashout_document_id, provider, model, status,
                         classification, schema_name, schema_version,
                         extracted_data_json, completed_at)
                    VALUES ('44444444-4444-4444-4444-444444444444',
                            '33333333-3333-3333-3333-333333333333', 'anthropic',
                            'some-model', 'needs_verification',
                            'server_summary_report', 'ServerSummaryReportData', 1,
                            '{"grand_total": "1.00"}'::jsonb, now());
                    """
                )
            )

        _upgrade(migrated_url, "head")

        nullability = _analysis_nullability(migrated_url)
        assert nullability["cropped_storage_key"] is True
        assert nullability["cropped_content_type"] is True
        assert nullability["crop_bounds"] is True
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT cropped_storage_key, cropped_content_type, crop_bounds"
                    " FROM cashout_document_analyses"
                )
            ).one()
            # Two analyses can never share a crop object.
            unique = conn.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE contype = 'u'"
                    " AND conname = 'cashout_document_analyses_cropped_storage_key_key'"
                )
            ).scalar_one()
        assert tuple(row) == (None, None, None)
        assert unique == 1
    finally:
        engine.dispose()


def test_upgrade_head_allows_several_analyses_per_upload(migrated_url: str) -> None:
    """An upload may carry one analysis per document found in it.

    The one-analysis-per-upload uniqueness becomes a plain index and every
    existing analysis is stamped its upload's first (position 1); a second
    position is accepted, and the same position twice is not.
    """
    # The last revision with one analysis per upload.
    _upgrade(migrated_url, "3e7a1c9d5f42")

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
                            '2026-09-01');
                    INSERT INTO cashout_documents
                        (id, cashout_submission_id, content_type, storage_key,
                         original_filename, checksum_sha256, uploaded_by_user_id,
                         uploaded_at)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            'image/jpeg', 'key', 'photo.jpg', 'checksum',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_document_analyses
                        (id, cashout_document_id, provider, model, status)
                    VALUES ('44444444-4444-4444-4444-444444444444',
                            '33333333-3333-3333-3333-333333333333', 'anthropic',
                            'some-model', 'extracting');
                    """
                )
            )

        _upgrade(migrated_url, "head")

        with engine.connect() as conn:
            position = conn.execute(
                text("SELECT position FROM cashout_document_analyses")
            ).scalar_one()
            indexdef = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname ="
                    " 'ix_cashout_document_analyses_cashout_upload_id'"
                )
            ).scalar_one()
        assert position == 1
        assert "UNIQUE" not in indexdef

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cashout_document_analyses
                        (id, cashout_upload_id, position, provider, model, status)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '33333333-3333-3333-3333-333333333333', 2, 'anthropic',
                            'some-model', 'extracting');
                    """
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cashout_document_analyses
                        (id, cashout_upload_id, position, provider, model, status)
                    VALUES ('66666666-6666-6666-6666-666666666666',
                            '33333333-3333-3333-3333-333333333333', 2, 'anthropic',
                            'some-model', 'extracting');
                    """
                )
            )
    finally:
        engine.dispose()


def _constraint_and_index_names(url: str, *tables: str) -> set[str]:
    """Every primary-key, foreign-key, and unique constraint name and every
    index name on the given tables."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            constraints = conn.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE contype IN ('p', 'f', 'u')"
                    " AND conrelid::regclass::text IN :tables"
                ).bindparams(bindparam("tables", expanding=True)),
                {"tables": list(tables)},
            )
            names = {row[0] for row in constraints}
            indexes = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE tablename IN :tables"
                ).bindparams(bindparam("tables", expanding=True)),
                {"tables": list(tables)},
            )
            return names | {row[0] for row in indexes}
    finally:
        engine.dispose()


# The names the rename revision moves between, in both directions. The old
# ones are what Postgres gave the initial migration's unnamed constraints;
# the new ones are what create_all gives the renamed model.
_RENAMED_NAMES = {
    "cashout_documents_pkey": "cashout_uploads_pkey",
    "cashout_documents_cashout_submission_id_fkey": (
        "cashout_uploads_cashout_submission_id_fkey"
    ),
    "cashout_documents_uploaded_by_user_id_fkey": (
        "cashout_uploads_uploaded_by_user_id_fkey"
    ),
    "cashout_documents_storage_key_key": "cashout_uploads_storage_key_key",
    "ix_cashout_documents_cashout_submission_id": (
        "ix_cashout_uploads_cashout_submission_id"
    ),
    "ix_cashout_documents_submission_checksum": (
        "ix_cashout_uploads_submission_checksum"
    ),
    "ix_cashout_documents_uploaded_by_user_id": (
        "ix_cashout_uploads_uploaded_by_user_id"
    ),
    "cashout_document_analyses_cashout_document_id_fkey": (
        "cashout_document_analyses_cashout_upload_id_fkey"
    ),
    "ix_cashout_document_analyses_cashout_document_id": (
        "ix_cashout_document_analyses_cashout_upload_id"
    ),
    "uq_cashout_document_analyses_document_position": (
        "uq_cashout_document_analyses_upload_position"
    ),
}


def test_upgrade_head_renames_documents_to_uploads(migrated_url: str) -> None:
    """The file a cashier submits is an upload: its table, and the analysis's
    reference to it, say so after `upgrade head`.

    A database holding an upload and its analysis comes out with the row in
    `cashout_uploads` and `cashout_upload_id` set on the analysis — renamed
    in place, not rebuilt — and every index and constraint renamed with them,
    so a migrated database matches a fresh install. The downgrade puts every
    name back.
    """
    # The last revision that still called the upload a document.
    _upgrade(migrated_url, "a1d4e7f92b36")
    tables = ("cashout_documents", "cashout_document_analyses")
    assert set(_RENAMED_NAMES) <= _constraint_and_index_names(migrated_url, *tables)

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
                            '2026-09-01');
                    INSERT INTO cashout_documents
                        (id, cashout_submission_id, content_type, storage_key,
                         original_filename, checksum_sha256, uploaded_by_user_id,
                         uploaded_at)
                    VALUES ('33333333-3333-3333-3333-333333333333',
                            '22222222-2222-2222-2222-222222222222',
                            'image/jpeg', 'key', 'photo.jpg', 'checksum',
                            '11111111-1111-1111-1111-111111111111', now());
                    INSERT INTO cashout_document_analyses
                        (id, cashout_document_id, provider, model, status)
                    VALUES ('44444444-4444-4444-4444-444444444444',
                            '33333333-3333-3333-3333-333333333333', 'anthropic',
                            'some-model', 'extracting');
                    """
                )
            )

        _upgrade(migrated_url, "head")

        assert "cashout_documents" not in inspect(engine).get_table_names()
        with engine.connect() as conn:
            upload_id = conn.execute(
                text("SELECT id::text FROM cashout_uploads")
            ).scalar_one()
            analysis_upload_id = conn.execute(
                text("SELECT cashout_upload_id::text FROM cashout_document_analyses")
            ).scalar_one()
        assert upload_id == "33333333-3333-3333-3333-333333333333"
        assert analysis_upload_id == upload_id
        tables = ("cashout_uploads", "cashout_document_analyses")
        names = _constraint_and_index_names(migrated_url, *tables)
        assert set(_RENAMED_NAMES.values()) <= names
        assert names.isdisjoint(_RENAMED_NAMES)

        _alembic(migrated_url, "downgrade", "a1d4e7f92b36")

        assert "cashout_uploads" not in inspect(engine).get_table_names()
        with engine.connect() as conn:
            analysis_document_id = conn.execute(
                text("SELECT cashout_document_id::text FROM cashout_document_analyses")
            ).scalar_one()
        assert analysis_document_id == upload_id
        tables = ("cashout_documents", "cashout_document_analyses")
        names = _constraint_and_index_names(migrated_url, *tables)
        assert set(_RENAMED_NAMES) <= names
        assert names.isdisjoint(_RENAMED_NAMES.values())
    finally:
        engine.dispose()


def test_upgrade_head_appends_the_adjustment_columns(migrated_url: str) -> None:
    """Data rows gain the two nullable adjustment columns; earlier rows carry
    none.

    A cashout closed before the deposit adjustment existed needed none, so
    `deposit_total` and `adjustment_note` come up null on it, and the
    reporting view grows the two appended columns without moving the sheet's
    nine.
    """
    # The last revision before the adjustment columns.
    _upgrade(migrated_url, "d26f1f11dc6a")
    assert "deposit_total" not in _data_nullability(migrated_url)

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
                         tipout_departments)
                    VALUES ('22222222-2222-2222-2222-222222222222',
                            '11111111-1111-1111-1111-111111111111', now(),
                            '2026-09-01',
                            ARRAY['expo', 'manager']::tipout_department[]);
                    INSERT INTO cashout_data
                        (id, submission_id, food_net_sales, drink_net_sales,
                         total_net_sales, card_payment_total,
                         cash_payment_total, card_tip_total,
                         tipout_departments, bar_tipout_rate,
                         kitchen_tipout_rate, expo_tipout_rate,
                         host_tipout_rate, manager_tipout_rate)
                    VALUES ('55555555-5555-5555-5555-555555555555',
                            '22222222-2222-2222-2222-222222222222',
                            800.00, 400.00, 1200.00, 1234.56, 150.00, 180.00,
                            ARRAY['expo', 'manager']::tipout_department[],
                            0.0500, 0.0300, 0.0100, 0.0100, 0.0100);
                    """
                )
            )

        _upgrade(migrated_url, "head")

        nullability = _data_nullability(migrated_url)
        assert nullability["deposit_total"] is True
        assert nullability["adjustment_note"] is True

        with engine.connect() as conn:
            deposit_total, adjustment_note, card_payment_total = conn.execute(
                text(
                    "SELECT deposit_total, adjustment_note, card_payment_total"
                    " FROM cashout_data"
                )
            ).one()
            view_columns = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_schema = 'reporting'"
                        " AND table_name = 'cashout_data'"
                        " ORDER BY ordinal_position"
                    )
                )
            ]
        # No adjustment on a cashout closed before there was such a thing;
        # its card payments are untouched.
        assert deposit_total is None
        assert adjustment_note is None
        assert str(card_payment_total) == "1234.56"
        # The sheet's nine columns stay where they were; the adjustment's
        # two are appended after everything else.
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


def test_gift_certificate_upgrade_and_downgrade_preserve_analyses(
    migrated_url: str,
) -> None:
    _upgrade(migrated_url, "e5a3c7d19f84")
    assert "gift_certificate" not in _enum_values(
        migrated_url, "cashout_document_classification"
    )
    _upgrade(migrated_url, "head")
    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO users (id, full_name, email)
                VALUES ('11111111-1111-1111-1111-111111111111', 'Cashier',
                        'cashier@test.com');
                INSERT INTO cashout_submissions
                    (id, employee_user_id, submitted_at, business_date)
                VALUES ('22222222-2222-2222-2222-222222222222',
                        '11111111-1111-1111-1111-111111111111', now(), '2026-09-11');
                INSERT INTO cashout_uploads
                    (id, cashout_submission_id, content_type, storage_key,
                     original_filename, checksum_sha256, uploaded_by_user_id,
                     uploaded_at)
                VALUES ('33333333-3333-3333-3333-333333333333',
                        '22222222-2222-2222-2222-222222222222',
                        'image/jpeg', 'key', 'gift.jpg', 'checksum',
                        '11111111-1111-1111-1111-111111111111', now());
                INSERT INTO cashout_document_analyses
                    (id, cashout_upload_id, status, classification, schema_name,
                     schema_version, extracted_data_json)
                VALUES ('44444444-4444-4444-4444-444444444444',
                        '33333333-3333-3333-3333-333333333333',
                        'needs_verification', 'gift_certificate',
                        'GiftCertificateData', 1, '{"amount": "25.00"}'::jsonb);
            """)
            )

        # Rolling back must fail rather than deleting or reclassifying a gift.
        with pytest.raises(AssertionError, match="gift_certificate"):
            _alembic(migrated_url, "downgrade", "e5a3c7d19f84")
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT classification::text, extracted_data_json "
                    "FROM cashout_document_analyses"
                )
            ).one()
            assert tuple(row) == ("gift_certificate", {"amount": "25.00"})

        with engine.begin() as conn:
            conn.execute(
                text("UPDATE cashout_document_analyses SET classification = NULL")
            )
        _alembic(migrated_url, "downgrade", "e5a3c7d19f84")
        assert _enum_values(migrated_url, "cashout_document_classification") == {
            "touchbistro_report",
            "server_summary_report",
        }
        _upgrade(migrated_url, "head")
        assert "gift_certificate" in _enum_values(
            migrated_url, "cashout_document_classification"
        )
    finally:
        engine.dispose()


def test_gift_certificate_upgrade_accepts_the_unversioned_rollout(
    migrated_url: str,
) -> None:
    _upgrade(migrated_url, "e5a3c7d19f84")
    engine = create_engine(migrated_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TYPE cashout_document_classification "
                    "ADD VALUE 'gift_certificate'"
                )
            )
        _upgrade(migrated_url, "head")
        assert "gift_certificate" in _enum_values(
            migrated_url, "cashout_document_classification"
        )
    finally:
        engine.dispose()
