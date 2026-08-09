"""passwordless login challenges

Revision ID: 909a0aeae0d7
Revises: e1c47a25d6b8
Create Date: 2026-08-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "909a0aeae0d7"
down_revision: Union[str, Sequence[str], None] = "e1c47a25d6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: login went passwordless and admin-created accounts
    replaced invitation registration, so both artifacts go away. The emailed
    login link now proves email access, so email verification (and the unused
    is_active flag) go with them."""
    op.drop_index(op.f("ix_invitations_invited_by_user_id"), table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "is_active")


def downgrade() -> None:
    """Downgrade schema: restore the columns (password_hash backfilled empty —
    the original hashes are unrecoverable; email_verified_at backfilled to
    created_at as 014cf69c312c did, so the old gate does not lock anyone out)
    and recreate the table as a2b0846eec7c built it."""
    op.add_column(
        "users",
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE users SET email_verified_at = created_at "
        "WHERE email_verified_at IS NULL"
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
    )
    op.create_table(
        "invitations",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"], unique=True)
    op.create_index(
        op.f("ix_invitations_invited_by_user_id"),
        "invitations",
        ["invited_by_user_id"],
        unique=False,
    )
