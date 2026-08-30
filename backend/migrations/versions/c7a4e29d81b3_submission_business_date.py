"""submission business date

Cashout submissions gain the day the cashout is *for* (business_date),
distinct from submitted_at (when it was opened): a cashier closing out after
midnight or catching up a missed day picks yesterday. Shipped as its own
revision (rather than an edit to the applied initial migration) so existing
databases pick the change up from `alembic upgrade head`.

Revision ID: c7a4e29d81b3
Revises: b1e7c40d9f52
Create Date: 2026-08-29 23:59:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a4e29d81b3"
down_revision: Union[str, Sequence[str], None] = "b1e7c40d9f52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Added nullable, backfilled, then constrained: existing rows never
    # recorded the intended day, so the (UTC) day they were opened is the
    # best available approximation for pre-feature rows.
    op.add_column(
        "cashout_submissions", sa.Column("business_date", sa.Date(), nullable=True)
    )
    op.execute(
        "UPDATE cashout_submissions"
        " SET business_date = (submitted_at AT TIME ZONE 'UTC')::date"
    )
    op.alter_column(
        "cashout_submissions",
        "business_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.create_index(
        op.f("ix_cashout_submissions_business_date"),
        "cashout_submissions",
        ["business_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cashout_submissions_business_date"),
        table_name="cashout_submissions",
    )
    op.drop_column("cashout_submissions", "business_date")
