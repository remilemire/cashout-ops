"""reconciled cashout data

Completing a cashout now reconciles its verified analyses into the source
figures, so a data row exists only once all six are known: they become NOT
NULL. Rows left over from before reconciliation carry none of them and cannot
be filled in from SQL, so their cashouts are reopened instead — exactly what
unsubmit does, leaving every analysis verified and one completion away from a
reconciled row. Shipped as its own revision (rather than an edit to the
applied initial migration) so existing databases pick the change up from
`alembic upgrade head`.

Revision ID: b1e7c40d9f52
Revises: 4c8f21d0a7b3
Create Date: 2026-08-29 23:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e7c40d9f52"
down_revision: Union[str, Sequence[str], None] = "4c8f21d0a7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_COLUMNS = (
    "food_net_sales",
    "drink_net_sales",
    "total_net_sales",
    "card_payment_total",
    "cash_payment_total",
    "card_tip_total",
)

# The six were always written together, but SET NOT NULL fails on any one of
# them, so the heal below matches on any one of them.
UNRECONCILED = " OR ".join(f"{column} IS NULL" for column in SOURCE_COLUMNS)


def upgrade() -> None:
    # Reopened before the rows go, and the same way unsubmit reopens one: the
    # completion timestamp and the tipout choice are kept, only who currently
    # completed it is cleared. `updated_at` is an ORM-level onupdate, so it is
    # stamped by hand here.
    op.execute(
        sa.text(
            f"""
            UPDATE cashout_submissions AS s
            SET status = 'processing',
                completed_by_user_id = NULL,
                updated_at = now()
            FROM cashout_data AS d
            WHERE d.submission_id = s.id AND ({UNRECONCILED})
            """
        )
    )
    op.execute(sa.text(f"DELETE FROM cashout_data WHERE {UNRECONCILED}"))

    for column in SOURCE_COLUMNS:
        op.alter_column(
            "cashout_data",
            column,
            existing_type=sa.Numeric(precision=12, scale=2),
            nullable=False,
        )


def downgrade() -> None:
    # Only the constraint comes back off; the cashouts reopened above stay
    # reopened, which is the state their (figure-less) rows described anyway.
    for column in SOURCE_COLUMNS:
        op.alter_column(
            "cashout_data",
            column,
            existing_type=sa.Numeric(precision=12, scale=2),
            nullable=True,
        )
