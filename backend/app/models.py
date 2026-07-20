from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    # visitor browsing needs no account; roles: user | subscriber | admin
    role = Column(String, default="user", nullable=False)
    # Grants access to the A/B tests section for non-admins. Admins always have
    # access regardless of this flag; it exists so the admin can hand a specific
    # signed-in person (e.g. a friend helping compare narration) the ability to
    # see all current and future A/B tests without making them an admin.
    ab_test_access = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at = Column(DateTime, default=datetime.utcnow)


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=True)
    filename = Column(String, nullable=False)
    pdf_path = Column(String, nullable=False)
    # pending → processing → synthesizing → complete | error
    status = Column(String, default="pending")
    # admin-only: hide from public listing (e.g. stuck/error books not yet ready)
    hidden = Column(Boolean, nullable=False, default=False, server_default="false")
    page_count = Column(Integer, nullable=True)
    genre = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    # admin-only: narrator preset key (voice + matching prompt); null → default.
    # See NARRATORS in app/services/tts.py.
    tts_narrator = Column(String, nullable=True)
    # admin-only: free-text narration prompt; overrides the preset's prompt (not
    # its voice) when set. Blank uses the preset.
    tts_instructions = Column(Text, nullable=True)
    # who uploaded the book; null for legacy books whose uploader is unknown
    uploaded_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    uploaded_by = relationship("User")

    segments = relationship(
        "Segment",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Segment.order",
    )


class PipelineEvent(Base):
    """A notable pipeline occurrence — mostly errors and warnings raised while
    ingesting or synthesizing a book. Written from both the web and worker
    droplets (they share this Postgres), so worker-side failures surface in the
    admin panel without the web tier ever reaching the worker directly."""

    __tablename__ = "pipeline_events"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable + SET NULL: an event outlives the book it referred to (e.g. a
    # book deleted after erroring) rather than being cascaded away.
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task = Column(String, nullable=False)  # e.g. "ingest_book", "synthesize_segment"
    level = Column(String, nullable=False, default="error", index=True)  # error | warning | info
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    order = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    # set on the first segment of each detected chapter; None elsewhere
    chapter_title = Column(String, nullable=True)
    # Primary narration (the book's chosen narrator preset). Alternate narrator
    # renditions live in `audios` (SegmentAudio) so listeners can toggle voices.
    audio_path = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | processing | ready | error
    duration = Column(Float, nullable=True)

    book = relationship("Book", back_populates="segments")
    audios = relationship(
        "SegmentAudio",
        back_populates="segment",
        cascade="all, delete-orphan",
    )


class SegmentAudio(Base):
    """An additional narrator rendition of a segment, beyond the primary one on
    the Segment row. One row per (segment, narrator preset); the listener picks
    which narration to hear and the audio router serves the matching take."""

    __tablename__ = "segment_audio"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(
        Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # narrator preset key — see NARRATORS in app/services/tts.py
    narrator = Column(String, nullable=False, index=True)
    audio_path = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending|processing|ready|error
    duration = Column(Float, nullable=True)

    segment = relationship("Segment", back_populates="audios")


class ABTest(Base):
    """A blind A/B listening comparison — two narration clips of the same
    passage that a permitted listener can play and pick a preference between.
    Used to compare TTS voices and prompt presets before committing to one.

    Visibility is gated at the section level (admin OR User.ab_test_access), not
    per-test, so granting someone access shows them every current and future
    test. `published` lets the admin stage a test before exposing it."""

    __tablename__ = "ab_tests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    options = relationship(
        "ABTestOption",
        back_populates="test",
        cascade="all, delete-orphan",
        order_by="ABTestOption.order",
    )
    votes = relationship(
        "ABTestVote", back_populates="test", cascade="all, delete-orphan"
    )


class ABTestOption(Base):
    """One side of an A/B test. `key` is the stable identifier a vote refers to
    ("A"/"B"); `label` is the human description shown only after voting / to the
    admin (e.g. "onyx", "alloy, no instructions"). `audio_key` is an R2 object
    key or a local storage path, resolved like book audio."""

    __tablename__ = "ab_test_options"

    id = Column(Integer, primary_key=True, index=True)
    ab_test_id = Column(
        Integer, ForeignKey("ab_tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String, nullable=False)  # "A" | "B"
    label = Column(String, nullable=False)
    audio_key = Column(String, nullable=True)
    order = Column(Integer, nullable=False, default=0)

    test = relationship("ABTest", back_populates="options")


class ABTestVote(Base):
    """A single listener's preference on a test. One row per (test, user) — a
    re-vote updates the existing row. `choice` is an option key ("A"/"B") or
    "no_diff" when the listener heard no meaningful difference."""

    __tablename__ = "ab_test_votes"
    __table_args__ = (
        UniqueConstraint("ab_test_id", "user_id", name="uq_ab_test_vote_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ab_test_id = Column(
        Integer, ForeignKey("ab_tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    choice = Column(String, nullable=False)  # "A" | "B" | "no_diff"
    created_at = Column(DateTime, default=datetime.utcnow)

    test = relationship("ABTest", back_populates="votes")
