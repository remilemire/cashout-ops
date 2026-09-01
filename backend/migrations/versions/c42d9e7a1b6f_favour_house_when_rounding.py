"""favour house when rounding

Each selected department's tipout is now rounded to cents toward positive
infinity before the final cash balance is calculated. The signed balance uses
the same rule, so a fractional employee obligation increases while a
fractional house obligation moves toward zero. Replacing the generated columns
recalculates existing cashouts in place.

Revision ID: c42d9e7a1b6f
Revises: a34f9c2d71be
Create Date: 2026-09-01 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c42d9e7a1b6f"
down_revision: Union[str, Sequence[str], None] = "a34f9c2d71be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _round_for_house_sql(expression: str) -> str:
    return f"(ceil(({expression}) * 100) / 100)"


_OLD_BAR_TIPOUT_SQL = "drink_net_sales * bar_tipout_rate"
_OLD_KITCHEN_TIPOUT_SQL = "food_net_sales * kitchen_tipout_rate"
_OLD_EXPO_TIPOUT_SQL = "total_net_sales * expo_tipout_rate"
_OLD_HOST_TIPOUT_SQL = "total_net_sales * host_tipout_rate"

_BAR_TIPOUT_SQL = _round_for_house_sql(_OLD_BAR_TIPOUT_SQL)
_KITCHEN_TIPOUT_SQL = _round_for_house_sql(_OLD_KITCHEN_TIPOUT_SQL)
_EXPO_TIPOUT_SQL = _round_for_house_sql(_OLD_EXPO_TIPOUT_SQL)
_HOST_TIPOUT_SQL = _round_for_house_sql(_OLD_HOST_TIPOUT_SQL)


def _selected_tipout_sql(department: str, amount_sql: str) -> str:
    return f"""
        CASE
            WHEN '{department}'::tipout_department = ANY(tipout_departments)
            THEN {amount_sql}
            ELSE 0
        END
    """


def _tipout_column_sql(department: str, amount_sql: str) -> str:
    return f"""
        CASE
            WHEN '{department}'::tipout_department = ANY(tipout_departments)
            THEN {amount_sql}
            ELSE NULL
        END
    """


_OLD_TOTAL_TIPOUT_SQL = " + ".join(
    (
        _selected_tipout_sql("bar", _OLD_BAR_TIPOUT_SQL),
        _selected_tipout_sql("kitchen", _OLD_KITCHEN_TIPOUT_SQL),
        _selected_tipout_sql("expo", _OLD_EXPO_TIPOUT_SQL),
        _selected_tipout_sql("host", _OLD_HOST_TIPOUT_SQL),
    )
)
_TOTAL_TIPOUT_SQL = " + ".join(
    (
        _selected_tipout_sql("bar", _BAR_TIPOUT_SQL),
        _selected_tipout_sql("kitchen", _KITCHEN_TIPOUT_SQL),
        _selected_tipout_sql("expo", _EXPO_TIPOUT_SQL),
        _selected_tipout_sql("host", _HOST_TIPOUT_SQL),
    )
)

_OLD_CASH_DUE_TO_HOUSE_SQL = (
    f"cash_payment_total - card_tip_total + ({_OLD_TOTAL_TIPOUT_SQL})"
)
_CASH_DUE_TO_HOUSE_SQL = _round_for_house_sql(
    f"cash_payment_total - card_tip_total + ({_TOTAL_TIPOUT_SQL})"
)


def _cash_column_sql(*, due_sql: str, house: bool) -> str:
    operator, result = (">", due_sql) if house else ("<", f"-({due_sql})")
    return f"""
        CASE
            WHEN ({due_sql}) {operator} 0
            THEN {result}
            ELSE NULL
        END
    """


_OLD_EXPRESSIONS = {
    "bar_tipout": _tipout_column_sql("bar", _OLD_BAR_TIPOUT_SQL),
    "kitchen_tipout": _tipout_column_sql("kitchen", _OLD_KITCHEN_TIPOUT_SQL),
    "expo_tipout": _tipout_column_sql("expo", _OLD_EXPO_TIPOUT_SQL),
    "host_tipout": _tipout_column_sql("host", _OLD_HOST_TIPOUT_SQL),
    "cash_owed_to_house": _cash_column_sql(
        due_sql=_OLD_CASH_DUE_TO_HOUSE_SQL, house=True
    ),
    "cash_owed_to_employee": _cash_column_sql(
        due_sql=_OLD_CASH_DUE_TO_HOUSE_SQL, house=False
    ),
}
_EXPRESSIONS = {
    "bar_tipout": _tipout_column_sql("bar", _BAR_TIPOUT_SQL),
    "kitchen_tipout": _tipout_column_sql("kitchen", _KITCHEN_TIPOUT_SQL),
    "expo_tipout": _tipout_column_sql("expo", _EXPO_TIPOUT_SQL),
    "host_tipout": _tipout_column_sql("host", _HOST_TIPOUT_SQL),
    "cash_owed_to_house": _cash_column_sql(due_sql=_CASH_DUE_TO_HOUSE_SQL, house=True),
    "cash_owed_to_employee": _cash_column_sql(
        due_sql=_CASH_DUE_TO_HOUSE_SQL, house=False
    ),
}


def _replace_generated_columns(expressions: dict[str, str]) -> None:
    # Cash columns are removed first and restored last: that order stays safe
    # if their expressions later refer directly to the tipout columns.
    for name in reversed(expressions):
        op.drop_column("cashout_data", name)
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


def upgrade() -> None:
    _replace_generated_columns(_EXPRESSIONS)


def downgrade() -> None:
    _replace_generated_columns(_OLD_EXPRESSIONS)
