"""case-insensitive emails

Mailboxes are case-insensitive, so the application now normalizes every
address to lowercase at the edges it can enter through (request bodies, the
BOOTSTRAP_OWNER_EMAIL setting, an issuer's verified claim). Stored rows
predate that rule and may hold mixed case, which ix_users_email — unique on
the exact string — would let sit beside its own lowercase twin as a second
account for one mailbox. Fold the stored values down to match.

The fold is refused rather than resolved when two rows already differ only
by casing: merging accounts means choosing which one's role and cashout
submissions survive, which is a human decision, not one a migration should
make silently on the identity table. The error names the addresses.

Shipped as its own revision (rather than an edit to the applied initial
migration) so existing databases pick the change up from
`alembic upgrade head`.

Revision ID: 9d3e5f81a2c4
Revises: c42d9e7a1b6f
Create Date: 2026-09-01 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d3e5f81a2c4"
down_revision: Union[str, Sequence[str], None] = "c42d9e7a1b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Soft-deleted rows are included: ix_users_email spans them, so a deleted
    # Foo@x.com would still collide with a live foo@x.com once folded, and
    # the reinvite path in users' service would revive the wrong one.
    collisions = (
        op.get_bind()
        .exec_driver_sql(
            """
            SELECT lower(email) AS mailbox, count(*) AS rows
            FROM users
            GROUP BY lower(email)
            HAVING count(*) > 1
            ORDER BY lower(email)
            """
        )
        .fetchall()
    )

    if collisions:
        listed = ", ".join(f"{row.mailbox} ({row.rows} rows)" for row in collisions)
        raise RuntimeError(
            "Cannot fold user emails to lowercase: these mailboxes already hold "
            f"more than one account — {listed}. Merge or remove the duplicates "
            "by hand (deciding which row keeps the role and the submissions "
            "pointing at its id), then re-run this migration."
        )

    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")


def downgrade() -> None:
    # Nothing to undo: the original casing is not recorded, and lowercase
    # addresses are valid under the previous case-sensitive schema.
    pass
