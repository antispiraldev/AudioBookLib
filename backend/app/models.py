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
    created_at = Column(DateTime, default=datetime.utcnow)

    segments = relationship(
        "Segment",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Segment.order",
    )


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    order = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    audio_path = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | processing | ready | error
    duration = Column(Float, nullable=True)

    book = relationship("Book", back_populates="segments")
