"""book owner (uploaded_by_user_id)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-18

Adds an uploader/owner reference to books. All pre-existing books predate any
owner tracking and were uploaded by the sole admin, so they are backfilled to
that account (looked up by email). New uploads capture the uploader going
forward (see books.upload_book).
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# The sole admin who uploaded every existing book. Backfill target.
LEGACY_OWNER_EMAIL = "lucavdelsignore@gmail.com"


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_books_uploaded_by_user_id_users",
        "books",
        "users",
        ["uploaded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_books_uploaded_by_user_id",
        "books",
        ["uploaded_by_user_id"],
    )
    # Backfill every existing book to the legacy owner. If that user row does
    # not exist yet (fresh DB), the subquery is NULL and books simply stay
    # owner-less — harmless, and the panel renders them as "—".
    op.execute(
        sa.text(
            "UPDATE books SET uploaded_by_user_id = "
            "(SELECT id FROM users WHERE lower(email) = lower(:email)) "
            "WHERE uploaded_by_user_id IS NULL"
        ).bindparams(email=LEGACY_OWNER_EMAIL)
    )


def downgrade() -> None:
    op.drop_index("ix_books_uploaded_by_user_id", table_name="books")
    op.drop_constraint(
        "fk_books_uploaded_by_user_id_users", "books", type_="foreignkey"
    )
    op.drop_column("books", "uploaded_by_user_id")
