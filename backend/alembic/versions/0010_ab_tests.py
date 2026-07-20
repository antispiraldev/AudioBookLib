"""A/B narration tests + per-user access flag

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20

Adds the A/B listening-test feature:

- users.ab_test_access — grants a non-admin the A/B tests section (admins
  always have access). Backfills existing rows to false.
- ab_tests / ab_test_options / ab_test_votes — a test, its two clips, and one
  preference row per (test, user).
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "ab_test_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "ab_tests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "published", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ab_tests_id", "ab_tests", ["id"])

    op.create_table(
        "ab_test_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ab_test_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("audio_key", sa.String(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["ab_test_id"], ["ab_tests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ab_test_options_id", "ab_test_options", ["id"])
    op.create_index(
        "ix_ab_test_options_ab_test_id", "ab_test_options", ["ab_test_id"]
    )

    op.create_table(
        "ab_test_votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ab_test_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("choice", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ab_test_id"], ["ab_tests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ab_test_id", "user_id", name="uq_ab_test_vote_user"
        ),
    )
    op.create_index("ix_ab_test_votes_id", "ab_test_votes", ["id"])
    op.create_index(
        "ix_ab_test_votes_ab_test_id", "ab_test_votes", ["ab_test_id"]
    )
    op.create_index("ix_ab_test_votes_user_id", "ab_test_votes", ["user_id"])


def downgrade() -> None:
    op.drop_table("ab_test_votes")
    op.drop_table("ab_test_options")
    op.drop_index("ix_ab_tests_id", table_name="ab_tests")
    op.drop_table("ab_tests")
    op.drop_column("users", "ab_test_access")
