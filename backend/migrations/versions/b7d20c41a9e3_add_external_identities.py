"""Add external identities

Revision ID: b7d20c41a9e3
Revises: 43450621e7c7
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d20c41a9e3"
down_revision: Union[str, Sequence[str], None] = "43450621e7c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: link OAuth issuer identities to local accounts.

    (issuer, subject) is unique — the issuer's subject claim is the durable
    identity key — and a user holds at most one identity per issuer. Links
    die with their user via the FK cascade. The sa.Enum column creates the
    oauth_issuer type with the table (the cbf386fc33b2 pattern); like there,
    it is never dropped automatically, so downgrade drops it explicitly.
    """
    op.create_table(
        "external_identities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "issuer",
            sa.Enum("google", name="oauth_issuer"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_identities_issuer_subject",
        "external_identities",
        ["issuer", "subject"],
        unique=True,
    )
    op.create_index(
        "ix_external_identities_user_issuer",
        "external_identities",
        ["user_id", "issuer"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_external_identities_user_issuer", table_name="external_identities"
    )
    op.drop_index(
        "ix_external_identities_issuer_subject", table_name="external_identities"
    )
    op.drop_table("external_identities")
    op.execute("DROP TYPE IF EXISTS oauth_issuer")
