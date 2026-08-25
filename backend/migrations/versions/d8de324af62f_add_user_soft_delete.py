"""Add user soft delete

Revision ID: d8de324af62f
Revises: c93e5f10ab84
Create Date: 2026-08-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8de324af62f"
down_revision: Union[str, Sequence[str], None] = "c93e5f10ab84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: users gain a nullable deleted_at soft-delete marker.

    Deleting a user who has cashout submissions cannot remove the row (their
    submissions' submitted_by_user_id FK still references it), so such
    accounts are deactivated by stamping deleted_at instead. NULL means the
    account is live; a stamped row is excluded from every live-account lookup
    but keeps the submission history's author intact.
    """
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "deleted_at")
