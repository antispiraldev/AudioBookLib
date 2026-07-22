"""Admin-only endpoints backing the pipeline-status panel.

Every route here is gated by `require_admin`. This module is the foundation
for the admin panel; later PRs add books/errors/workers/resources/logs
endpoints alongside the summary below.
"""
import os
import shutil
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    ABTest,
    ABTestOption,
    ABTestVote,
    Book,
    PipelineEvent,
    Segment,
    User,
)
from ..schemas import (
    AdminBookRow,
    AdminUserRow,
    PipelineEventOut,
    UserAccessUpdate,
)
from ..services import storage
from ..services.monitor import (
    read_web_logs,
    read_worker_logs,
    resource_report,
    worker_stats,
)
from .auth import require_admin

STORAGE_AB_AUDIO = "storage/ab_audio"
os.makedirs(STORAGE_AB_AUDIO, exist_ok=True)

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


@router.get("/workers")
def admin_workers():
    """Live Celery/queue snapshot: broker reachability, default-queue depth,
    and per-worker concurrency + running tasks. Sync on purpose — the inspect
    broadcast blocks up to ~1s, and FastAPI runs sync routes in a thread."""
    return worker_stats()


@router.get("/resources")
def admin_resources():
    """Host resources for both droplets with ok/warn/critical severity — web
    read live via psutil, worker from its heartbeat key in Redis."""
    return resource_report()


@router.get("/logs")
def admin_logs(
    source: str = Query("web", pattern="^(web|worker)$"),
    limit: int = Query(200, ge=10, le=1000),
):
    """Recent log lines, chronological — the web backend's rotating file, or
    the worker's Redis-shipped lines."""
    lines = read_web_logs(limit) if source == "web" else read_worker_logs(limit)
    return {"source": source, "lines": lines}


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


# --- Access management -------------------------------------------------------


@router.get("/users", response_model=List[AdminUserRow])
def admin_users(db: Session = Depends(get_db)):
    """Everyone who has signed in, so the admin can grant/revoke A/B access."""
    return db.query(User).order_by(User.id.asc()).all()


@router.patch("/users/{user_id}", response_model=AdminUserRow)
def admin_update_user(
    user_id: int,
    body: UserAccessUpdate,
    db: Session = Depends(get_db),
):
    """Grant or revoke a user's A/B tests access."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.ab_test_access = body.ab_test_access
    db.commit()
    db.refresh(user)
    return user


# --- A/B test management -----------------------------------------------------


def _save_option_audio(option: ABTestOption, upload: UploadFile) -> None:
    """Persist an uploaded clip for an option: R2 in prod, local otherwise.
    Requires option.id, so call after the row is flushed."""
    if storage.is_enabled():
        local = os.path.join(STORAGE_AB_AUDIO, f"{option.id}.mp3")
        with open(local, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        key = f"ab_tests/{option.id}.mp3"
        storage.upload(local, key)
        os.remove(local)
        option.audio_key = key
    else:
        path = os.path.join(STORAGE_AB_AUDIO, f"{option.id}.mp3")
        with open(path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        option.audio_key = path


def _serialize_admin_test(test: ABTest, tallies: dict[int, dict]) -> dict:
    counts = tallies.get(test.id, {})
    total = sum(counts.values())
    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "published": test.published,
        "created_at": test.created_at,
        "options": [
            {"id": o.id, "key": o.key, "label": o.label} for o in test.options
        ],
        "results": {
            "A": counts.get("A", 0),
            "B": counts.get("B", 0),
            "no_diff": counts.get("no_diff", 0),
            "total": total,
        },
    }


@router.get("/ab-tests")
def admin_list_ab_tests(db: Session = Depends(get_db)):
    """All A/B tests (published or not) with per-choice vote tallies."""
    tests = db.query(ABTest).order_by(ABTest.created_at.desc()).all()
    rows = (
        db.query(ABTestVote.ab_test_id, ABTestVote.choice, func.count(ABTestVote.id))
        .group_by(ABTestVote.ab_test_id, ABTestVote.choice)
        .all()
    )
    tallies: dict[int, dict] = {}
    for test_id, choice, count in rows:
        tallies.setdefault(test_id, {})[choice] = count
    return [_serialize_admin_test(t, tallies) for t in tests]


@router.post("/ab-tests")
def admin_create_ab_test(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    label_a: str = Form(...),
    label_b: str = Form(...),
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    published: bool = Form(True),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a two-clip A/B test. Both clips are uploaded here and stored
    alongside book audio (R2 in prod)."""
    test = ABTest(
        title=title,
        description=description,
        published=published,
        created_by_user_id=admin.id,
    )
    opt_a = ABTestOption(key="A", label=label_a, order=0)
    opt_b = ABTestOption(key="B", label=label_b, order=1)
    test.options = [opt_a, opt_b]
    db.add(test)
    db.flush()  # assign ids before naming the audio objects

    _save_option_audio(opt_a, file_a)
    _save_option_audio(opt_b, file_b)
    db.commit()
    db.refresh(test)
    return _serialize_admin_test(test, {})


@router.delete("/ab-tests/{test_id}", status_code=204)
def admin_delete_ab_test(test_id: int, db: Session = Depends(get_db)):
    """Delete a test, its options, votes, and stored clips."""
    test = db.get(ABTest, test_id)
    if not test:
        raise HTTPException(404, "Test not found")

    for option in test.options:
        if not option.audio_key:
            continue
        if storage.is_r2_key(option.audio_key):
            storage.delete_prefix(option.audio_key)
        elif os.path.exists(option.audio_key):
            os.remove(option.audio_key)

    db.delete(test)  # cascades to options + votes
    db.commit()
