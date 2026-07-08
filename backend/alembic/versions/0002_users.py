"""users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("google_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("google_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])


def downgrade() -> None:
    op.drop_table("users")
