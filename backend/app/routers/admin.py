"""Admin-only endpoints backing the pipeline-status panel.

Every route here is gated by `require_admin`. This module is the foundation
for the admin panel; later PRs add books/errors/workers/resources/logs
endpoints alongside the summary below.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book
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
