"""Reshape cashout_data around tipouts

Revision ID: 4e8b21c7af35
Revises: 7d3c1b0f52ae
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4e8b21c7af35"
down_revision: Union[str, Sequence[str], None] = "7d3c1b0f52ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The four placeholder columns this replaces were never written — reconcile
# only ever set submission_id — so no existing row carries a figure worth
# migrating.

_DEPARTMENTS = ("bar", "kitchen", "expo", "host")

_DROPPED = ("daily_tipout", "net_total", "cash_total", "card_total")

# Source figures reconciled off the verified analyses. Nullable for now:
# reconciliation is not written yet, and a row with these null is simply an
# unreconciled cashout. They become NOT NULL with that change.
_SOURCES = (
    "food_net_sales",
    "drink_net_sales",
    "total_net_sales",
    "card_payment_total",
    "cash_payment_total",
    "card_tip_total",
)

# The per-department rates in force at completion, copied onto the row: a rate
# change must not silently restate a cashout that already closed. NUMERIC(6, 4)
# because these are fractions of sales, not amounts — at cent precision a 3.5%
# rate would store as 4%. Existing rows take the current configured rates as a
# one-off backfill; they carry no figures for those rates to act on.
_RATES = {
    "bar_tipout_rate": "0.0500",
    "kitchen_tipout_rate": "0.0300",
    "expo_tipout_rate": "0.0100",
    "host_tipout_rate": "0.0100",
}

# Generated from the columns above, so each tipout is frozen against the rate
# its own row captured. A department the cashier did not select stays NULL,
# which is what records the selection — there is no separate list to keep in
# step. Kept in sync with data/model.py by hand; Postgres only supports STORED.
_COMPUTED: tuple[tuple[str, str], ...] = (
    (
        "bar_tipout",
        "CASE WHEN 'bar'::tipout_department = ANY(tipout_departments)"
        " THEN drink_net_sales * bar_tipout_rate ELSE NULL END",
    ),
    (
        "kitchen_tipout",
        "CASE WHEN 'kitchen'::tipout_department = ANY(tipout_departments)"
        " THEN food_net_sales * kitchen_tipout_rate ELSE NULL END",
    ),
    (
        "expo_tipout",
        "CASE WHEN 'expo'::tipout_department = ANY(tipout_departments)"
        " THEN total_net_sales * expo_tipout_rate ELSE NULL END",
    ),
    (
        "host_tipout",
        "CASE WHEN 'host'::tipout_department = ANY(tipout_departments)"
        " THEN total_net_sales * host_tipout_rate ELSE NULL END",
    ),
    (
        "cash_owed_to_house",
        "CASE WHEN cash_payment_total > card_tip_total"
        " THEN cash_payment_total - card_tip_total ELSE NULL END",
    ),
    (
        "cash_owed_to_employee",
        "CASE WHEN card_tip_total > cash_payment_total"
        " THEN card_tip_total - cash_payment_total ELSE NULL END",
    ),
)


def _department_array() -> postgresql.ARRAY[str]:
    # create_type=False: the enum is created and dropped explicitly below, so
    # the column DDL must not try to manage it a second time.
    return postgresql.ARRAY(
        postgresql.ENUM(*_DEPARTMENTS, name="tipout_department", create_type=False)
    )


def upgrade() -> None:
    """Replace the placeholder columns with the reconciled tipout shape."""
    labels = ", ".join(f"'{value}'" for value in _DEPARTMENTS)
    op.execute(f"CREATE TYPE tipout_department AS ENUM ({labels})")

    for column in _DROPPED:
        op.drop_column("cashout_data", column)

    # Sources and rates first: the generated columns read them.
    for column in _SOURCES:
        op.add_column("cashout_data", sa.Column(column, sa.Numeric(12, 2)))

    # The NOT NULL columns carry a default only long enough to admit rows that
    # already exist; it is dropped below so every future row states its own.
    for column, rate in _RATES.items():
        op.add_column(
            "cashout_data",
            sa.Column(column, sa.Numeric(6, 4), nullable=False, server_default=rate),
        )
    op.add_column(
        "cashout_data",
        sa.Column(
            "tipout_departments",
            _department_array(),
            nullable=False,
            server_default="{}",
        ),
    )

    for column, expression in _COMPUTED:
        op.add_column(
            "cashout_data",
            sa.Column(column, sa.Numeric(12, 2), sa.Computed(expression)),
        )

    for column in (*_RATES, "tipout_departments"):
        op.alter_column("cashout_data", column, server_default=None)


def downgrade() -> None:
    """Restore the placeholder columns (the tipout figures are not recoverable)."""
    for column, _ in _COMPUTED:
        op.drop_column("cashout_data", column)
    op.drop_column("cashout_data", "tipout_departments")
    for column in (*_RATES, *_SOURCES):
        op.drop_column("cashout_data", column)

    op.execute("DROP TYPE tipout_department")

    for column in _DROPPED:
        op.add_column(
            "cashout_data", sa.Column(column, sa.Numeric(12, 2), nullable=True)
        )
