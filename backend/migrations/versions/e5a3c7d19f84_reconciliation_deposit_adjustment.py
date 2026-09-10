"""reconciliation deposit adjustment

Completion cross-checks the server summaries' grand totals against the
TouchBistro report's card payments. A deposit the report counts among its
card payments never shows on a terminal summary, so such a cashout could not
complete. An admin may now subtract that deposit before the cross-check, and
the data row keeps what was done: `deposit_total` (the amount subtracted) and
`adjustment_note` (why), both nullable — null on every existing row and on
every cashout that needed no adjustment. `card_payment_total` stays the
report's own figure, and no generated column reads the new ones.

This revision defines the current `reporting.cashout_data`: the two
adjustment columns are appended after the manager's, because the management
sheet reads the first nine by position. A later migration that rebuilds a
column the view reads drops it first via
`view_defined_in("e5a3c7d19f84", "cashout_data_view")` and recreates it
afterwards.

Revision ID: e5a3c7d19f84
Revises: d26f1f11dc6a
Create Date: 2026-09-10 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.views import ReplaceableView, create_view, drop_view, view_defined_in

# revision identifiers, used by Alembic.
revision: str = "e5a3c7d19f84"
down_revision: Union[str, Sequence[str], None] = "d26f1f11dc6a"
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
            d.host_tipout_rate::double precision          AS host_tipout_rate,

            -- The manager tipout (on every cashout) and its rate. Appended here
            -- rather than placed among the money columns above: the sheet reads
            -- the first nine columns by position, so nothing before them may move.
            d.manager_tipout::double precision            AS manager_tipout,
            d.manager_tipout_rate::double precision       AS manager_tipout_rate,

            -- An admin's adjustment to the cross-check: the deposit subtracted
            -- from the report's card payments, and the note left with it. NULL
            -- when the cashout needed none. Appended last, for the same reason:
            -- the sheet reads the first nine columns by position.
            d.deposit_total::double precision             AS deposit_total,
            d.adjustment_note                             AS adjustment_note
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
            ' the API row, with the manager tipout and its rate, then the'
            ' reconciliation adjustment (deposit and note), appended last.'
        """,
        "GRANT SELECT ON reporting.cashout_data TO reporting_reader",
    ),
)


def upgrade() -> None:
    # The view is rebuilt to append the new columns; it goes first so the
    # table change and the new definition land together.
    drop_view(view_defined_in("b8e1d47c5a92", "cashout_data_view"))
    op.add_column(
        "cashout_data",
        sa.Column("deposit_total", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "cashout_data", sa.Column("adjustment_note", sa.Text(), nullable=True)
    )
    create_view(cashout_data_view)


def downgrade() -> None:
    # The view reads the columns being dropped, so it must be gone first.
    drop_view(cashout_data_view)
    op.drop_column("cashout_data", "adjustment_note")
    op.drop_column("cashout_data", "deposit_total")
    create_view(view_defined_in("b8e1d47c5a92", "cashout_data_view"))
