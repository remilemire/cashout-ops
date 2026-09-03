"""reporting cashout data view

A read-only reporting surface for the management Google Sheet: the
`reporting` schema; `reporting.cashout_data`, a view mirroring the admin
"Cashout data" table (GET /api/cashout/data) — one row per reconciled
cashout, newest first; and `reporting_reader`, a NOLOGIN group role that may
read the view and nothing else. The sheet's own login role is created by hand
as a member of that group.

The view is a migration-managed object (see migrations/views.py): Postgres
refuses to drop a column a view reads, so a later migration that rebuilds one
of the columns below must drop the view first and recreate it afterwards, via
`view_defined_in("9b2f6e1d4a73", "cashout_data_view")`.

Revision ID: 9b2f6e1d4a73
Revises: 9d3e5f81a2c4
Create Date: 2026-09-03 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

from migrations.views import ReplaceableView, create_view, drop_view

# revision identifiers, used by Alembic.
revision: str = "9b2f6e1d4a73"
down_revision: Union[str, Sequence[str], None] = "9d3e5f81a2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

cashout_data_view = ReplaceableView(
    "reporting.cashout_data",
    select="""
        SELECT
            -- The table's columns, in its column order ----------------------------
            --
            -- Who the cashout was for, and its business day. The day is the ISO text
            -- the API sends ("2026-08-10"): a date-typed column is parsed as local
            -- midnight by some drivers and then shifted a day; text never is.
            u.full_name                                   AS employee_name,
            to_char(s.business_date, 'YYYY-MM-DD')        AS business_date,

            -- Money, in the table's order. NULL where the department was not tipped
            -- out, or that side of the cash balance is not owed (the page shows a
            -- dash there, never $0.00). Cast to double precision so every driver
            -- delivers a number: some return numeric as text, which a spreadsheet
            -- cannot sum. Cent values survive the cast exactly as Sheets would store
            -- them anyway.
            d.kitchen_tipout::double precision            AS kitchen_tipout,
            d.bar_tipout::double precision                AS bar_tipout,
            d.expo_tipout::double precision               AS expo_tipout,
            d.host_tipout::double precision               AS host_tipout,
            d.cash_owed_to_house::double precision        AS cash_owed_to_house,
            d.cash_owed_to_employee::double precision     AS cash_owed_to_employee,

            -- The table's order: 1 is the top row (newest reconciled cashout first,
            -- as the API lists them). Sort ascending on this in the sheet.
            row_number() OVER (ORDER BY d.created_at DESC, d.id)::integer
                                                          AS display_order,

            -- The rest of the API row, for reference -----------------------------
            d.id::text                                    AS cashout_data_id,
            d.created_at                                  AS created_at,
            d.submission_id::text                         AS submission_id,
            u.id::text                                    AS employee_id,
            u.email                                       AS employee_email,
            u.role::text                                  AS employee_role,

            -- The reconciled source figures from the TouchBistro report.
            d.food_net_sales::double precision            AS food_net_sales,
            d.drink_net_sales::double precision           AS drink_net_sales,
            d.total_net_sales::double precision           AS total_net_sales,
            d.card_payment_total::double precision        AS card_payment_total,
            d.cash_payment_total::double precision        AS cash_payment_total,
            d.card_tip_total::double precision            AS card_tip_total,

            -- The departments tipped out, and the rates the cashout closed against.
            array_to_string(d.tipout_departments, ', ')   AS tipout_departments,
            d.bar_tipout_rate::double precision           AS bar_tipout_rate,
            d.kitchen_tipout_rate::double precision       AS kitchen_tipout_rate,
            d.expo_tipout_rate::double precision          AS expo_tipout_rate,
            d.host_tipout_rate::double precision          AS host_tipout_rate
        FROM public.cashout_data AS d
        JOIN public.cashout_submissions AS s ON s.id = d.submission_id
        JOIN public.users AS u ON u.id = s.employee_user_id
        -- No deleted_at filters, like the API: a data row exists only for a live,
        -- completed submission (unsubmit removes the row before a cashout can be
        -- deleted), and a deactivated employee still appears on their cashouts.
        ORDER BY d.created_at DESC, d.id
    """,
    after_create=(
        """
        COMMENT ON VIEW reporting.cashout_data IS
            'The admin "Cashout data" table (GET /api/cashout/data): one row per'
            ' reconciled cashout, newest first. The first nine columns feed the'
            ' management Google Sheet by position; the rest are the remainder of'
            ' the API row.'
        """,
        "GRANT SELECT ON reporting.cashout_data TO reporting_reader",
    ),
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA reporting")
    op.execute(
        "COMMENT ON SCHEMA reporting IS 'Read-only reporting views for spreadsheet"
        " consumers (the management Google Sheet).'"
    )

    # Roles are cluster-wide, not per database, so the group may already exist:
    # after a downgrade (which leaves it in place, see below), or on a server
    # shared by several databases, like the test suite's Postgres container.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_reader') THEN
                CREATE ROLE reporting_reader NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA reporting TO reporting_reader")

    # The view's after_create issues its COMMENT and the GRANT SELECT. That is
    # deliberately the reader's only table privilege — nothing on schema
    # public or any table: the view reads them with its owner's privileges.
    create_view(cashout_data_view)


def downgrade() -> None:
    drop_view(cashout_data_view)
    op.execute("DROP SCHEMA reporting")
    # The role stays: it is cluster-wide, inert without grants, and dropping it
    # would also take the sheet's login role out of the group — a membership
    # that would otherwise have to be restored by hand after re-upgrading.
