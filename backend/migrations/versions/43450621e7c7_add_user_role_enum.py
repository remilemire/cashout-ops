"""add user role enum

Revision ID: 43450621e7c7
Revises: 909a0aeae0d7
Create Date: 2026-08-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "43450621e7c7"
down_revision: Union[str, Sequence[str], None] = "909a0aeae0d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Created explicitly on upgrade and dropped on downgrade (autogenerate-created
# enum types are never dropped automatically — see cbf386fc33b2).
_USER_ROLE = postgresql.ENUM("staff", "admin", "owner", name="user_role")


def upgrade() -> None:
    """Upgrade schema: the is_admin boolean becomes the user_role enum
    (staff/admin/owner). Existing admins keep admin access; the FIRST-created
    admin (the bootstrapped account) becomes the single owner, enforced by the
    ix_users_single_owner partial unique index."""
    _USER_ROLE.create(op.get_bind())
    op.add_column(
        "users",
        sa.Column(
            "role",
            postgresql.ENUM(
                "staff", "admin", "owner", name="user_role", create_type=False
            ),
            server_default="staff",
            nullable=False,
        ),
    )
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin")
    op.execute(
        "UPDATE users SET role = 'owner' WHERE id = ("
        "SELECT id FROM users WHERE is_admin ORDER BY created_at ASC, id ASC LIMIT 1"
        ")"
    )
    op.drop_column("users", "is_admin")
    op.create_index(
        "ix_users_single_owner",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )


def downgrade() -> None:
    """Downgrade schema: restore is_admin (the owner maps back to a plain
    admin — the single-owner distinction is not representable)."""
    op.drop_index("ix_users_single_owner", table_name="users")
    op.add_column(
        "users",
        sa.Column(
            "is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute("UPDATE users SET is_admin = true WHERE role IN ('admin', 'owner')")
    op.drop_column("users", "role")
    _USER_ROLE.drop(op.get_bind())
