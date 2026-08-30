"""one live cashout per day

Each employee may hold at most one live cashout per business day, enforced by
a partial unique index on (employee_user_id, business_date) WHERE deleted_at
IS NULL — partial so a cancelled (soft-deleted) cashout doesn't block opening
a new one for the same day. Existing databases may already hold same-day
duplicates (the business_date backfill gave same-day submissions the same
date), so the upgrade first soft-deletes all but one live row per (employee,
day) before creating the index. Shipped as its own revision (rather than an
edit to the applied initial migration) so existing databases pick the change
up from `alembic upgrade head`.

Revision ID: e8f4a2b19c67
Revises: c7a4e29d81b3
Create Date: 2026-08-29 23:59:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f4a2b19c67"
down_revision: Union[str, Sequence[str], None] = "c7a4e29d81b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the best live row per (employee, day) and soft-delete the rest: a
    # completed cashout outranks drafts (it holds the day's reconciled data,
    # and the app refuses to delete it), then the newest wins. Soft-delete is
    # the app's own cancel semantics — reversible by nulling deleted_at.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY employee_user_id, business_date
                ORDER BY (status = 'completed') DESC, submitted_at DESC, id
            ) AS rn
            FROM cashout_submissions
            WHERE deleted_at IS NULL
        )
        UPDATE cashout_submissions s
        SET deleted_at = now()
        FROM ranked r
        WHERE s.id = r.id AND r.rn > 1
        """
    )
    op.create_index(
        "ix_cashout_submissions_employee_business_date",
        "cashout_submissions",
        ["employee_user_id", "business_date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Drops the index only: the rows the upgrade soft-deleted are not
    # resurrected — which duplicates were live then is not recorded, and a
    # human can null deleted_at by hand if one is ever wanted back.
    op.drop_index(
        "ix_cashout_submissions_employee_business_date",
        table_name="cashout_submissions",
    )
