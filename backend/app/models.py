from sqlalchemy import Boolean, Column, Integer, String, Text, Float, DateTime, ForeignKey
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
    audio_path = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | processing | ready | error
    duration = Column(Float, nullable=True)

    book = relationship("Book", back_populates="segments")
