"""pipeline events

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-18

A log of notable pipeline occurrences (errors/warnings) written from both the
web and worker droplets, surfaced in the admin panel.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "book_id",
            sa.Integer(),
            sa.ForeignKey("books.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False, server_default="error"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_pipeline_events_book_id", "pipeline_events", ["book_id"])
    op.create_index("ix_pipeline_events_level", "pipeline_events", ["level"])
    op.create_index("ix_pipeline_events_created_at", "pipeline_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_events_created_at", table_name="pipeline_events")
    op.drop_index("ix_pipeline_events_level", table_name="pipeline_events")
    op.drop_index("ix_pipeline_events_book_id", table_name="pipeline_events")
    op.drop_table("pipeline_events")
