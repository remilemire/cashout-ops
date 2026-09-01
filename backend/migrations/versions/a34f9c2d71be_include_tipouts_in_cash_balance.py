"""include tipouts in cash balance

The final cash balance now includes every selected tipout: tipouts increase
what the employee owes the house and reduce what the house owes the employee.
Both generated columns are replaced so existing reconciled rows are
recalculated in place when the migration runs.

Revision ID: a34f9c2d71be
Revises: d2b8a4e91c05
Create Date: 2026-09-01 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a34f9c2d71be"
down_revision: Union[str, Sequence[str], None] = "d2b8a4e91c05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOTAL_TIPOUT_SQL = """
    (
        CASE
            WHEN 'bar'::tipout_department = ANY(tipout_departments)
            THEN drink_net_sales * bar_tipout_rate
            ELSE 0
        END
        + CASE
            WHEN 'kitchen'::tipout_department = ANY(tipout_departments)
            THEN food_net_sales * kitchen_tipout_rate
            ELSE 0
        END
        + CASE
            WHEN 'expo'::tipout_department = ANY(tipout_departments)
            THEN total_net_sales * expo_tipout_rate
            ELSE 0
        END
        + CASE
            WHEN 'host'::tipout_department = ANY(tipout_departments)
            THEN total_net_sales * host_tipout_rate
            ELSE 0
        END
    )
"""

_CASH_DUE_TO_HOUSE_SQL = f"""
    (cash_payment_total - card_tip_total + {_TOTAL_TIPOUT_SQL})
"""

_CASH_OWED_TO_HOUSE_SQL = f"""
    CASE
        WHEN {_CASH_DUE_TO_HOUSE_SQL} > 0
        THEN {_CASH_DUE_TO_HOUSE_SQL}
        ELSE NULL
    END
"""

_CASH_OWED_TO_EMPLOYEE_SQL = f"""
    CASE
        WHEN {_CASH_DUE_TO_HOUSE_SQL} < 0
        THEN -{_CASH_DUE_TO_HOUSE_SQL}
        ELSE NULL
    END
"""

_OLD_CASH_OWED_TO_HOUSE_SQL = """
    CASE
        WHEN cash_payment_total > card_tip_total
        THEN cash_payment_total - card_tip_total
        ELSE NULL
    END
"""

_OLD_CASH_OWED_TO_EMPLOYEE_SQL = """
    CASE
        WHEN card_tip_total > cash_payment_total
        THEN card_tip_total - cash_payment_total
        ELSE NULL
    END
"""


def _replace_cash_columns(
    *,
    house_sql: str,
    employee_sql: str,
) -> None:
    # PostgreSQL cannot alter a generated expression in place. These columns
    # contain no independent data, so replacing them safely recomputes every
    # existing row from its source figures and snapshotted rates.
    op.drop_column("cashout_data", "cash_owed_to_house")
    op.drop_column("cashout_data", "cash_owed_to_employee")
    op.add_column(
        "cashout_data",
        sa.Column(
            "cash_owed_to_house",
            sa.Numeric(precision=12, scale=2),
            sa.Computed(house_sql),
            nullable=True,
        ),
    )
    op.add_column(
        "cashout_data",
        sa.Column(
            "cash_owed_to_employee",
            sa.Numeric(precision=12, scale=2),
            sa.Computed(employee_sql),
            nullable=True,
        ),
    )


def upgrade() -> None:
    _replace_cash_columns(
        house_sql=_CASH_OWED_TO_HOUSE_SQL,
        employee_sql=_CASH_OWED_TO_EMPLOYEE_SQL,
    )


def downgrade() -> None:
    _replace_cash_columns(
        house_sql=_OLD_CASH_OWED_TO_HOUSE_SQL,
        employee_sql=_OLD_CASH_OWED_TO_EMPLOYEE_SQL,
    )
