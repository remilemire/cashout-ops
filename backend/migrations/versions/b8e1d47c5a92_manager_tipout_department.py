"""manager tipout department

Two changes to the tipout rules. The manager now tips out on every cashout, at
1% of total net sales: `manager` joins the `tipout_department` enum, every data
row carries a `manager_tipout_rate` snapshot and a generated `manager_tipout`,
and the cash balance includes it. Expo now tips out on food net sales rather
than total net sales.

Both changes reach cashouts already closed: `manager` is appended to every
department list (the data rows and the submissions' last-completion
snapshots), the new rate column is backfilled at 1%, and replacing the
generated columns recalculates expo, the manager tipout, and the cash balance
in place — so an existing cashout's `cash_owed_*` moves.

The enum is rebuilt rather than extended: the chain runs inside one
transaction, and Postgres refuses to use a value added by ALTER TYPE ... ADD
VALUE before that transaction commits, whereas this revision uses `manager`
straight away. Postgres also refuses to recast a column a generated column
reads, so the generated columns come off first — they are being replaced
anyway.

This revision defines the current `reporting.cashout_data`: the two manager
columns are appended after the last existing column, because the management
sheet reads the first nine by position. A later migration that rebuilds a
column the view reads drops it first via
`view_defined_in("b8e1d47c5a92", "cashout_data_view")` and recreates it
afterwards.

Revision ID: b8e1d47c5a92
Revises: 9b2f6e1d4a73
Create Date: 2026-09-05 10:00:00.000000

"""

from collections.abc import Mapping
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.views import ReplaceableView, create_view, drop_view, view_defined_in

# revision identifiers, used by Alembic.
revision: str = "b8e1d47c5a92"
down_revision: Union[str, Sequence[str], None] = "9b2f6e1d4a73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUM_NAME = "tipout_department"
OLD_DEPARTMENTS = ("bar", "kitchen", "expo", "host")
DEPARTMENTS = (*OLD_DEPARTMENTS, "manager")

# Every column typed on the enum: the submission's last-completion snapshot
# and the data row's authoritative list.
ARRAY_COLUMNS = (
    ("cashout_submissions", "tipout_departments"),
    ("cashout_data", "tipout_departments"),
)


def _round_for_house_sql(expression: str) -> str:
    return f"(ceil(({expression}) * 100) / 100)"


_BAR_TIPOUT_SQL = _round_for_house_sql("drink_net_sales * bar_tipout_rate")
_KITCHEN_TIPOUT_SQL = _round_for_house_sql("food_net_sales * kitchen_tipout_rate")
_OLD_EXPO_TIPOUT_SQL = _round_for_house_sql("total_net_sales * expo_tipout_rate")
_EXPO_TIPOUT_SQL = _round_for_house_sql("food_net_sales * expo_tipout_rate")
_HOST_TIPOUT_SQL = _round_for_house_sql("total_net_sales * host_tipout_rate")
_MANAGER_TIPOUT_SQL = _round_for_house_sql("total_net_sales * manager_tipout_rate")

# Each department's amount, keyed by department, before and after.
_OLD_AMOUNTS: dict[str, str] = {
    "bar": _BAR_TIPOUT_SQL,
    "kitchen": _KITCHEN_TIPOUT_SQL,
    "expo": _OLD_EXPO_TIPOUT_SQL,
    "host": _HOST_TIPOUT_SQL,
}
_AMOUNTS: dict[str, str] = {
    "bar": _BAR_TIPOUT_SQL,
    "kitchen": _KITCHEN_TIPOUT_SQL,
    "expo": _EXPO_TIPOUT_SQL,
    "host": _HOST_TIPOUT_SQL,
    "manager": _MANAGER_TIPOUT_SQL,
}


def _selected_tipout_sql(department: str, amount_sql: str) -> str:
    return f"""
        CASE
            WHEN '{department}'::{ENUM_NAME} = ANY(tipout_departments)
            THEN {amount_sql}
            ELSE 0
        END
    """


def _tipout_column_sql(department: str, amount_sql: str) -> str:
    return f"""
        CASE
            WHEN '{department}'::{ENUM_NAME} = ANY(tipout_departments)
            THEN {amount_sql}
            ELSE NULL
        END
    """


def _cash_column_sql(*, due_sql: str, house: bool) -> str:
    operator, result = (">", due_sql) if house else ("<", f"-({due_sql})")
    return f"""
        CASE
            WHEN ({due_sql}) {operator} 0
            THEN {result}
            ELSE NULL
        END
    """


def _generated_expressions(amounts: Mapping[str, str]) -> dict[str, str]:
    """Every generated column of cashout_data, in creation order, for the
    given department amounts: one tipout column per department, then the two
    sides of the cash balance."""
    total_sql = " + ".join(
        _selected_tipout_sql(department, amount_sql)
        for department, amount_sql in amounts.items()
    )
    due_sql = _round_for_house_sql(
        f"cash_payment_total - card_tip_total + ({total_sql})"
    )
    return {
        **{
            f"{department}_tipout": _tipout_column_sql(department, amount_sql)
            for department, amount_sql in amounts.items()
        },
        "cash_owed_to_house": _cash_column_sql(due_sql=due_sql, house=True),
        "cash_owed_to_employee": _cash_column_sql(due_sql=due_sql, house=False),
    }


_OLD_EXPRESSIONS = _generated_expressions(_OLD_AMOUNTS)
_EXPRESSIONS = _generated_expressions(_AMOUNTS)


def _drop_generated_columns(names: Sequence[str]) -> None:
    # Cash columns are removed first: that order stays safe if their
    # expressions later refer directly to the tipout columns.
    for name in reversed(names):
        op.drop_column("cashout_data", name)


def _add_generated_columns(expressions: Mapping[str, str]) -> None:
    for name, expression in expressions.items():
        op.add_column(
            "cashout_data",
            sa.Column(
                name,
                sa.Numeric(precision=12, scale=2),
                sa.Computed(expression),
                nullable=True,
            ),
        )


def _replace_enum(values: Sequence[str]) -> None:
    """Swap the department enum for one over exactly `values`, recasting every
    array column onto it. Callable only while no generated column reads those
    columns (see the module docstring)."""
    members = ", ".join(f"'{value}'" for value in values)
    op.execute(f"ALTER TYPE {ENUM_NAME} RENAME TO {ENUM_NAME}_old")
    op.execute(f"CREATE TYPE {ENUM_NAME} AS ENUM ({members})")
    for table, column in ARRAY_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {ENUM_NAME}[] "
            f"USING {column}::text[]::{ENUM_NAME}[]"
        )
    op.execute(f"DROP TYPE {ENUM_NAME}_old")


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
            d.manager_tipout_rate::double precision       AS manager_tipout_rate
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
            ' the API row, with the manager tipout and its rate appended last.'
        """,
        "GRANT SELECT ON reporting.cashout_data TO reporting_reader",
    ),
)


def upgrade() -> None:
    # The view reads the generated columns and the department list, so it
    # must be gone before either is touched.
    drop_view(view_defined_in("9b2f6e1d4a73", "cashout_data_view"))
    _drop_generated_columns(tuple(_OLD_EXPRESSIONS))
    _replace_enum(DEPARTMENTS)

    # NOT NULL needs a value for the rows already there: 1%, the rate the
    # manager tips out at from now on, so every closed cashout is restated as
    # if it had. The default then goes — the application supplies the rate on
    # every row it writes, and the ORM column declares none.
    op.add_column(
        "cashout_data",
        sa.Column(
            "manager_tipout_rate",
            sa.Numeric(precision=6, scale=4),
            server_default=sa.text("0.0100"),
            nullable=False,
        ),
    )
    op.alter_column("cashout_data", "manager_tipout_rate", server_default=None)

    # Every existing list gains the manager, matching what reconciliation
    # writes from now on ('manager' sorts last, as sorted() would place it).
    for table, column in ARRAY_COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = array_append({column}, 'manager') "
            f"WHERE {column} IS NOT NULL AND NOT ('manager' = ANY({column}))"
        )

    _add_generated_columns(_EXPRESSIONS)
    create_view(cashout_data_view)


def downgrade() -> None:
    drop_view(cashout_data_view)
    _drop_generated_columns(tuple(_EXPRESSIONS))

    # The recast below refuses a list still holding a value the old enum lacks.
    for table, column in ARRAY_COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = array_remove({column}, 'manager') "
            f"WHERE {column} IS NOT NULL"
        )
    _replace_enum(OLD_DEPARTMENTS)

    # Only now: the manager and cash columns referred to it until dropped above.
    op.drop_column("cashout_data", "manager_tipout_rate")

    _add_generated_columns(_OLD_EXPRESSIONS)
    create_view(view_defined_in("9b2f6e1d4a73", "cashout_data_view"))
