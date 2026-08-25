"""Submission first completed at

Revision ID: 932beaca5e6e
Revises: 092735cdcf28
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "932beaca5e6e"
down_revision: Union[str, Sequence[str], None] = "092735cdcf28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: first_completed_by_user_id becomes first_completed_at.

    The set-once-never-cleared "completed at least once" marker changes from a
    user FK to a timestamp. The exact first-completion time was never recorded,
    so the backfill is best-effort: updated_at stands in for rows with a first
    completer on record (the closest approximation available). Dropping the
    column drops its auto-named FK constraint with it.
    """
    op.add_column(
        "cashout_submissions",
        sa.Column("first_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE cashout_submissions SET first_completed_at = updated_at "
        "WHERE first_completed_by_user_id IS NOT NULL"
    )
    op.drop_index(
        op.f("ix_cashout_submissions_first_completed_by_user_id"),
        table_name="cashout_submissions",
    )
    op.drop_column("cashout_submissions", "first_completed_by_user_id")


def downgrade() -> None:
    """Downgrade schema.

    The first completer's identity was not preserved, so the backfill is lossy:
    completed_by_user_id (the most recent completer) stands in for the first,
    and stays NULL for submissions sitting unsubmitted at downgrade time.
    """
    # Inline REFERENCES so Postgres auto-names the FK, matching the unnamed
    # ForeignKey() convention of the initial schema.
    op.add_column(
        "cashout_submissions",
        sa.Column(
            "first_completed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_cashout_submissions_first_completed_by_user_id"),
        "cashout_submissions",
        ["first_completed_by_user_id"],
        unique=False,
    )
    op.execute(
        "UPDATE cashout_submissions SET first_completed_by_user_id = "
        "completed_by_user_id WHERE first_completed_at IS NOT NULL"
    )
    op.drop_column("cashout_submissions", "first_completed_at")
