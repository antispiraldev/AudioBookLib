"""Admin-only endpoints backing the pipeline-status panel.

Every route here is gated by `require_admin`. This module is the foundation
for the admin panel; later PRs add books/errors/workers/resources/logs
endpoints alongside the summary below.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, PipelineEvent, Segment, User
from ..schemas import AdminBookRow, PipelineEventOut
from .auth import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])

# Every status a Book can hold, so the summary always reports a full set of
# counts (0 included) rather than omitting statuses that happen to be empty.
BOOK_STATUSES = [
    "pending",
    "processing",
    "review",
    "synthesizing",
    "complete",
    "error",
]


@router.get("/summary")
def pipeline_summary(db: Session = Depends(get_db)):
    """Book counts per status, plus the total — the panel's top-line strip."""
    rows = (
        db.query(Book.status, func.count(Book.id))
        .group_by(Book.status)
        .all()
    )
    counts = {status: 0 for status in BOOK_STATUSES}
    for status, count in rows:
        # Tolerate any unexpected/legacy status value rather than dropping it.
        counts[status] = counts.get(status, 0) + count
    return {"total": sum(counts.values()), "by_status": counts}


@router.get("/books", response_model=List[AdminBookRow])
def admin_books(db: Session = Depends(get_db)):
    """Every book as a lightweight table row — status, owner, and segment
    progress counts. Deliberately excludes segment text/audio payloads; the
    per-status counts are aggregated in SQL so this stays cheap for the poll."""
    # Segment progress per book, computed in one grouped query.
    seg = (
        db.query(
            Segment.book_id.label("book_id"),
            func.count(Segment.id).label("total"),
            func.sum(case((Segment.status == "ready", 1), else_=0)).label("ready"),
            func.sum(case((Segment.status == "error", 1), else_=0)).label("error"),
        )
        .group_by(Segment.book_id)
        .subquery()
    )

    rows = (
        db.query(
            Book,
            User.email.label("owner_email"),
            seg.c.total,
            seg.c.ready,
            seg.c.error,
        )
        .outerjoin(User, Book.uploaded_by_user_id == User.id)
        .outerjoin(seg, seg.c.book_id == Book.id)
        .order_by(Book.created_at.desc())
        .all()
    )

    return [
        AdminBookRow(
            id=book.id,
            title=book.title,
            author=book.author,
            status=book.status,
            genre=book.genre,
            year=book.year,
            hidden=book.hidden,
            page_count=book.page_count,
            created_at=book.created_at,
            owner_email=owner_email,
            segments_total=total or 0,
            segments_ready=ready or 0,
            segments_error=error or 0,
        )
        for book, owner_email, total, ready, error in rows
    ]


@router.get("/events", response_model=List[PipelineEventOut])
def admin_events(
    level: Optional[str] = None,
    book_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Recent pipeline events (errors/warnings), newest first. Optionally
    filtered by level or book. Joins the book title for display; events whose
    book was since deleted keep a null title."""
    q = (
        db.query(PipelineEvent, Book.title)
        .outerjoin(Book, PipelineEvent.book_id == Book.id)
    )
    if level:
        q = q.filter(PipelineEvent.level == level)
    if book_id is not None:
        q = q.filter(PipelineEvent.book_id == book_id)
    rows = q.order_by(PipelineEvent.created_at.desc()).limit(limit).all()

    return [
        PipelineEventOut(
            id=ev.id,
            book_id=ev.book_id,
            book_title=title,
            task=ev.task,
            level=ev.level,
            message=ev.message,
            traceback=ev.traceback,
            created_at=ev.created_at,
        )
        for ev, title in rows
    ]
