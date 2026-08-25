"""Submission ownership rework

Revision ID: 6f89b4881598
Revises: d8de324af62f
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f89b4881598"
down_revision: Union[str, Sequence[str], None] = "d8de324af62f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: rename the submitter FK and add completion bookkeeping.

    cashout_submissions.submitted_by_user_id becomes employee_user_id (an
    in-place rename, so data survives), with its index and FK constraint
    renamed to match. Admins can now complete anyone's cashout, so the
    completing user is recorded: completed_by_user_id holds the most recent
    completer and first_completed_by_user_id the first (set once). updated_at
    refreshes on every ORM update; the server default backfills existing rows.
    """
    op.alter_column(
        "cashout_submissions",
        "submitted_by_user_id",
        new_column_name="employee_user_id",
    )
    op.execute(
        "ALTER INDEX ix_cashout_submissions_submitted_by_user_id "
        "RENAME TO ix_cashout_submissions_employee_user_id"
    )
    op.execute(
        "ALTER TABLE cashout_submissions "
        "RENAME CONSTRAINT cashout_submissions_submitted_by_user_id_fkey "
        "TO cashout_submissions_employee_user_id_fkey"
    )

    # Inline REFERENCES so Postgres auto-names the FKs, matching the unnamed
    # ForeignKey() convention of the initial schema.
    op.add_column(
        "cashout_submissions",
        sa.Column(
            "completed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "cashout_submissions",
        sa.Column(
            "first_completed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "cashout_submissions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_cashout_submissions_completed_by_user_id"),
        "cashout_submissions",
        ["completed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashout_submissions_first_completed_by_user_id"),
        "cashout_submissions",
        ["first_completed_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_cashout_submissions_first_completed_by_user_id"),
        table_name="cashout_submissions",
    )
    op.drop_index(
        op.f("ix_cashout_submissions_completed_by_user_id"),
        table_name="cashout_submissions",
    )
    # drop_column drops the auto-named FK constraints with the columns.
    op.drop_column("cashout_submissions", "updated_at")
    op.drop_column("cashout_submissions", "first_completed_by_user_id")
    op.drop_column("cashout_submissions", "completed_by_user_id")

    op.execute(
        "ALTER TABLE cashout_submissions "
        "RENAME CONSTRAINT cashout_submissions_employee_user_id_fkey "
        "TO cashout_submissions_submitted_by_user_id_fkey"
    )
    op.execute(
        "ALTER INDEX ix_cashout_submissions_employee_user_id "
        "RENAME TO ix_cashout_submissions_submitted_by_user_id"
    )
    op.alter_column(
        "cashout_submissions",
        "employee_user_id",
        new_column_name="submitted_by_user_id",
    )
