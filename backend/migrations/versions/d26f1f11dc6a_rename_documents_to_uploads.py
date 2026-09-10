"""rename cashout documents to uploads

An upload — the file a cashier submits — may hold several documents, and an
analysis stands for each document found in it. The table holding the file
was still `cashout_documents`, and the analysis's reference to it
`cashout_document_id`, so "document" named both the file and the printed
thing. This renames the file's table, the column pointing at it, and their
indexes and constraints to say upload; `cashout_document_analyses` keeps its
name (an analysis is of a document). Pure renames, so every row, storage
key, and enum type survives and an existing database picks the change up
from `alembic upgrade head`.

Revision ID: d26f1f11dc6a
Revises: a1d4e7f92b36
Create Date: 2026-09-10 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d26f1f11dc6a"
down_revision: Union[str, Sequence[str], None] = "a1d4e7f92b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (old, new) index names. Renaming a unique constraint below renames the
# index behind it as well, so those are listed once, as constraints.
_INDEXES = [
    (
        "ix_cashout_documents_cashout_submission_id",
        "ix_cashout_uploads_cashout_submission_id",
    ),
    (
        "ix_cashout_documents_submission_checksum",
        "ix_cashout_uploads_submission_checksum",
    ),
    (
        "ix_cashout_documents_uploaded_by_user_id",
        "ix_cashout_uploads_uploaded_by_user_id",
    ),
    (
        "ix_cashout_document_analyses_cashout_document_id",
        "ix_cashout_document_analyses_cashout_upload_id",
    ),
]

# (table after the rename, old, new) constraint names. The old ones are
# Postgres's own names for the initial migration's unnamed constraints,
# confirmed against a migrated database; the new ones are what create_all
# gives the renamed model, so a fresh install and a migrated one match.
_CONSTRAINTS = [
    ("cashout_uploads", "cashout_documents_pkey", "cashout_uploads_pkey"),
    (
        "cashout_uploads",
        "cashout_documents_cashout_submission_id_fkey",
        "cashout_uploads_cashout_submission_id_fkey",
    ),
    (
        "cashout_uploads",
        "cashout_documents_uploaded_by_user_id_fkey",
        "cashout_uploads_uploaded_by_user_id_fkey",
    ),
    (
        "cashout_uploads",
        "cashout_documents_storage_key_key",
        "cashout_uploads_storage_key_key",
    ),
    (
        "cashout_document_analyses",
        "cashout_document_analyses_cashout_document_id_fkey",
        "cashout_document_analyses_cashout_upload_id_fkey",
    ),
    (
        "cashout_document_analyses",
        "uq_cashout_document_analyses_document_position",
        "uq_cashout_document_analyses_upload_position",
    ),
]


def upgrade() -> None:
    op.rename_table("cashout_documents", "cashout_uploads")
    op.alter_column(
        "cashout_document_analyses",
        "cashout_document_id",
        new_column_name="cashout_upload_id",
    )
    for old, new in _INDEXES:
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    for table, old, new in _CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def downgrade() -> None:
    for table, old, new in reversed(_CONSTRAINTS):
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}")
    for old, new in reversed(_INDEXES):
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    op.alter_column(
        "cashout_document_analyses",
        "cashout_upload_id",
        new_column_name="cashout_document_id",
    )
    op.rename_table("cashout_uploads", "cashout_documents")
