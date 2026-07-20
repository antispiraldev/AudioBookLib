"""alternate narration takes per segment

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20

A segment's primary narration lives on the segment row itself
(Segment.audio_path), rendered in the book's chosen narrator preset. This table
holds *additional* narrator renditions of the same segment so a listener can
toggle voices. One row per (segment, narrator); FK cascade so a segment's takes
are cleaned up whenever the segment is deleted (reprocess wipes segments in bulk,
which bypasses the ORM cascade — the DB-level cascade is what actually clears
these).
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_audio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "segment_id",
            sa.Integer(),
            sa.ForeignKey("segments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("narrator", sa.String(), nullable=False),
        sa.Column("audio_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.UniqueConstraint("segment_id", "narrator", name="uq_segment_audio_seg_narr"),
    )
    op.create_index("ix_segment_audio_segment_id", "segment_audio", ["segment_id"])
    op.create_index("ix_segment_audio_narrator", "segment_audio", ["narrator"])


def downgrade() -> None:
    op.drop_index("ix_segment_audio_narrator", table_name="segment_audio")
    op.drop_index("ix_segment_audio_segment_id", table_name="segment_audio")
    op.drop_table("segment_audio")
