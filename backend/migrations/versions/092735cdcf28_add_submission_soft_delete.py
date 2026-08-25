"""Add submission soft delete

Revision ID: 092735cdcf28
Revises: 6f89b4881598
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "092735cdcf28"
down_revision: Union[str, Sequence[str], None] = "6f89b4881598"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: submissions gain a nullable deleted_at soft-delete marker.

    A submission with traces (documents, reconciled data, or a completion on
    record) cannot simply be removed — its documents, analyses, and user FKs
    are history worth keeping. Deleting such a submission stamps deleted_at
    instead; every submission lookup excludes stamped rows, so it behaves as
    gone. NULL means the row is live.
    """
    op.add_column(
        "cashout_submissions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cashout_submissions", "deleted_at")
