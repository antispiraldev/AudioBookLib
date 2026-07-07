"""initial schema — books and segments

Revision ID: 0001
Revises:
Create Date: 2026-07-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("pdf_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("genre", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_books_id", "books", ["id"])

    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("audio_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
    )
    op.create_index("ix_segments_id", "segments", ["id"])
    op.create_index("ix_segments_book_id", "segments", ["book_id"])


def downgrade() -> None:
    op.drop_table("segments")
    op.drop_table("books")
