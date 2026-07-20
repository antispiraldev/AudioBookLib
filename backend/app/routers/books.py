import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, Segment, SegmentAudio, User
from ..schemas import BookOut, BookUpdate, NarrationOut, SegmentText, SegmentUpdate
from ..services import storage, tts
from ..services.suggest import suggest_metadata
from ..tasks import ingest_book, synthesize_book, synthesize_narration
from .auth import get_current_user, require_admin

log = logging.getLogger(__name__)

router = APIRouter()

STORAGE_PDF = "storage/pdfs"

os.makedirs(STORAGE_PDF, exist_ok=True)


def _is_admin(user: Optional[User]) -> bool:
    return user is not None and user.role == "admin"


def _primary_narrator(book: Book) -> str:
    return book.tts_narrator or tts.DEFAULT_NARRATOR


def _alt_counts(db: Session, book_ids: List[int]) -> dict:
    """Ready-take counts for alternate narrations, keyed [book_id][narrator].
    One grouped query for the whole page so listing books stays O(1) queries."""
    counts: dict = {}
    if not book_ids:
        return counts
    rows = (
        db.query(Segment.book_id, SegmentAudio.narrator, func.count())
        .join(SegmentAudio, SegmentAudio.segment_id == Segment.id)
        .filter(Segment.book_id.in_(book_ids), SegmentAudio.status == "ready")
        .group_by(Segment.book_id, SegmentAudio.narrator)
        .all()
    )
    for book_id, narrator, n in rows:
        counts.setdefault(book_id, {})[narrator] = n
    return counts


def _narrations_for(book: Book, alt_ready: dict) -> List[NarrationOut]:
    """Build a book's selectable narration list: the primary narrator (audio on
    the segments) plus any alternate narrator with rendered takes. `alt_ready`
    maps narrator → ready-take count for this book."""
    total = len(book.segments)
    base_ready = sum(1 for s in book.segments if s.status == "ready")

    primary_key = _primary_narrator(book)
    p = tts.preset(primary_key)
    out = [
        NarrationOut(
            narrator=primary_key,
            label=p["label"],
            voice=p["voice"],
            primary=True,
            ready=total > 0 and base_ready == total,
            segments_ready=base_ready,
            segments_total=total,
        )
    ]
    # Alternates target the ready base segments; order them as NARRATORS defines.
    for key, preset in tts.NARRATORS.items():
        if key == primary_key or key not in alt_ready:
            continue
        ready_n = min(alt_ready[key], base_ready)
        out.append(
            NarrationOut(
                narrator=key,
                label=preset["label"],
                voice=preset["voice"],
                primary=False,
                ready=base_ready > 0 and ready_n >= base_ready,
                segments_ready=ready_n,
                segments_total=base_ready,
            )
        )
    return out


def _with_narrations(book: Book, db: Session) -> Book:
    """Attach the computed narrations list to a single book instance so BookOut
    (from_attributes) serializes it."""
    book.narrations = _narrations_for(book, _alt_counts(db, [book.id]).get(book.id, {}))
    return book


@router.get("/", response_model=List[BookOut])
def list_books(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    q = db.query(Book).order_by(Book.created_at.desc())
    if not _is_admin(user):
        q = q.filter(Book.hidden.is_(False))
    books = q.all()
    counts = _alt_counts(db, [b.id for b in books])
    for b in books:
        b.narrations = _narrations_for(b, counts.get(b.id, {}))
    return books


@router.get("/narrators", dependencies=[Depends(require_admin)])
def list_narrators():
    """Narrator presets the admin can assign to a book (key, label, voice)."""
    return {
        "default": tts.DEFAULT_NARRATOR,
        "presets": [
            {"key": key, "label": p["label"], "voice": p["voice"]}
            for key, p in tts.NARRATORS.items()
        ],
    }


@router.get("/{book_id}", response_model=BookOut)
def get_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    if book.hidden and not _is_admin(user):
        raise HTTPException(404, "Book not found")
    return _with_narrations(book, db)


@router.post("/", response_model=BookOut)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    pdf_path = os.path.join(STORAGE_PDF, file.filename)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    book = Book(
        title=title,
        author=author,
        filename=file.filename,
        pdf_path=pdf_path,
        uploaded_by_user_id=admin.id,
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    if storage.is_enabled():
        key = f"pdfs/{book.id}/{file.filename}"
        storage.upload(pdf_path, key)
        os.remove(pdf_path)
        book.pdf_path = key
        db.commit()
        db.refresh(book)

    ingest_book.delay(book.id)
    return _with_narrations(book, db)


@router.patch("/{book_id}", response_model=BookOut, dependencies=[Depends(require_admin)])
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return _with_narrations(book, db)


@router.get(
    "/{book_id}/segments",
    response_model=List[SegmentText],
    dependencies=[Depends(require_admin)],
)
def list_book_segments(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return (
        db.query(Segment)
        .filter(Segment.book_id == book_id)
        .order_by(Segment.order)
        .all()
    )


@router.patch(
    "/{book_id}/segments/{order}",
    response_model=SegmentText,
    dependencies=[Depends(require_admin)],
)
def update_book_segment(
    book_id: int, order: int, data: SegmentUpdate, db: Session = Depends(get_db)
):
    seg = (
        db.query(Segment)
        .filter(Segment.book_id == book_id, Segment.order == order)
        .first()
    )
    if not seg:
        raise HTTPException(404, "Segment not found")
    seg.text = data.text
    # Edited text needs re-synthesis; drop any stale audio on the next approve.
    seg.status = "pending"
    db.commit()
    db.refresh(seg)
    return seg


@router.get("/{book_id}/suggest", dependencies=[Depends(require_admin)])
def suggest_book_metadata(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    first_segment = (
        db.query(Segment)
        .filter(Segment.book_id == book_id)
        .order_by(Segment.order)
        .first()
    )
    excerpt = first_segment.text if first_segment else ""
    try:
        with storage.local_pdf(book.pdf_path) as pdf_path:
            return suggest_metadata(pdf_path, book.title, excerpt)
    except Exception as e:
        log.exception("suggest_metadata failed for book %d", book_id)
        raise HTTPException(502, f"Suggestion failed: {e}")


@router.post("/{book_id}/synthesize", response_model=BookOut, dependencies=[Depends(require_admin)])
def retry_synthesize(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    # Flip to synthesizing in the response itself (synthesize_book also does this
    # worker-side, but only once it runs). Without this the API returns the book
    # still in review/error, so the UI keeps showing Approve until the next poll —
    # a window where a second click fires a duplicate synthesis run.
    synthesize_book.delay(book_id)
    book.status = "synthesizing"
    db.commit()
    db.refresh(book)
    return _with_narrations(book, db)


class NarrationRequest(BaseModel):
    narrator: str


@router.post(
    "/{book_id}/narrations",
    response_model=BookOut,
    dependencies=[Depends(require_admin)],
)
def add_narration(book_id: int, data: NarrationRequest, db: Session = Depends(get_db)):
    """Kick off rendering an additional narrator's take of a complete book, so
    listeners can toggle voices. Idempotent — re-posting a narrator retries any
    missing/errored segments without re-paying for takes already rendered."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    if data.narrator not in tts.NARRATORS:
        raise HTTPException(400, "Unknown narrator preset")
    if data.narrator == _primary_narrator(book):
        raise HTTPException(400, "That narrator is already the book's primary narration")
    if not any(s.status == "ready" for s in book.segments):
        raise HTTPException(400, "Book has no rendered audio yet — synthesize it first")

    synthesize_narration.delay(book_id, data.narrator)
    return _with_narrations(book, db)


@router.delete(
    "/{book_id}/narrations/{narrator}",
    response_model=BookOut,
    dependencies=[Depends(require_admin)],
)
def delete_narration(book_id: int, narrator: str, db: Session = Depends(get_db)):
    """Remove an alternate narration (its rows + stored audio). The primary
    narration lives on the segments and can't be dropped here."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    if narrator == _primary_narrator(book):
        raise HTTPException(400, "Can't delete the primary narration")

    storage.delete_prefix(f"audio/{book_id}/{narrator}/")
    local_dir = os.path.join("storage", "audio", str(book_id), narrator)
    if os.path.isdir(local_dir):
        shutil.rmtree(local_dir, ignore_errors=True)
    seg_ids = [s.id for s in book.segments]
    if seg_ids:
        db.query(SegmentAudio).filter(
            SegmentAudio.segment_id.in_(seg_ids),
            SegmentAudio.narrator == narrator,
        ).delete(synchronize_session=False)
        db.commit()
    db.refresh(book)
    return _with_narrations(book, db)


# Archived audio takes (from past reprocesses) — the pre-tuning "original"
# recordings live here. They were rendered against an older, coarser
# segmentation, so they don't line up with the current segments and can't join
# the listener voice toggle. This is an admin-only way to listen back to them.
_TS_RE = re.compile(r"^\d{8}T\d{6}Z$")
_PART_RE = re.compile(r"^\d{4}\.mp3$")


def _format_ts(ts: str) -> str:
    """20260717T102253Z → '2026-07-17 10:22 UTC' for a readable label."""
    try:
        dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ts


@router.get("/{book_id}/archives", dependencies=[Depends(require_admin)])
def list_archives(book_id: int, db: Session = Depends(get_db)):
    """Archived audio takes for a book, grouped by the reprocess timestamp that
    produced them (newest first). Each entry lists its part filenames so the
    admin UI can play through the take."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    takes: dict[str, list[str]] = {}
    for key in storage.list_prefix(f"audio-archive/{book_id}/"):
        # key: audio-archive/{book_id}/{ts}/{part}
        parts = key.split("/")
        if len(parts) < 4:
            continue
        ts, name = parts[2], parts[3]
        if _TS_RE.match(ts) and _PART_RE.match(name):
            takes.setdefault(ts, []).append(name)

    return [
        {"ts": ts, "label": _format_ts(ts), "parts": sorted(names)}
        for ts, names in sorted(takes.items(), reverse=True)
    ]


@router.get(
    "/{book_id}/archives/{ts}/{part}",
    dependencies=[Depends(require_admin)],
)
def stream_archive(book_id: int, ts: str, part: str, db: Session = Depends(get_db)):
    """Stream one part of an archived take (admin only)."""
    if not _TS_RE.match(ts) or not _PART_RE.match(part):
        raise HTTPException(404, "Not found")
    key = f"audio-archive/{book_id}/{ts}/{part}"
    if storage.is_enabled():
        return RedirectResponse(storage.presigned_url(key, expiry=3600), status_code=302)
    path = os.path.join("storage", key)
    if not os.path.exists(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="audio/mpeg")


def _clear_generated(book_id: int, db: Session) -> None:
    """Drop a book's segments so ingest can rebuild cleanly, archiving the
    existing audio rather than deleting it — resynthesis costs real money and
    R2 storage is cheap, so a bad reprocess never destroys a paid-for take."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    storage.archive_prefix(f"audio/{book_id}/", f"audio-archive/{book_id}/{ts}/")
    local_audio = os.path.join("storage", "audio", str(book_id))
    if os.path.isdir(local_audio):
        dst = os.path.join("storage", "audio-archive", str(book_id), ts)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(local_audio, dst)
    db.query(Segment).filter(Segment.book_id == book_id).delete()
    db.commit()


@router.post("/{book_id}/reprocess", response_model=BookOut, dependencies=[Depends(require_admin)])
async def reprocess_book(
    book_id: int,
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Re-extract and re-clean a book with the current pipeline, back to review.

    Clears existing segments and audio, then re-runs ingest. Migrated books
    whose source PDF is gone must attach it here — the upload is persisted to
    R2 so the book is never stranded again.
    """
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    if file is not None:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are supported")
        # Drop any old copies first, then store the new PDF where the old one lived.
        storage.delete_prefix(f"pdfs/{book_id}/")
        if book.pdf_path.startswith("storage/") and os.path.exists(book.pdf_path):
            os.remove(book.pdf_path)

        local_path = os.path.join(STORAGE_PDF, file.filename)
        with open(local_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        book.filename = file.filename
        if storage.is_enabled():
            key = f"pdfs/{book_id}/{file.filename}"
            storage.upload(local_path, key)
            os.remove(local_path)
            book.pdf_path = key
        else:
            book.pdf_path = local_path
        db.commit()
    elif not storage.pdf_available(book.pdf_path):
        raise HTTPException(
            400,
            "Source PDF is unavailable — attach the PDF file to reprocess this book.",
        )

    _clear_generated(book_id, db)
    book.status = "pending"
    book.page_count = None
    db.commit()
    db.refresh(book)

    ingest_book.delay(book_id)
    return _with_narrations(book, db)


@router.delete("/{book_id}", dependencies=[Depends(require_admin)])
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    # A true, complete delete — including any archived takes from past reprocesses.
    storage.delete_prefix(f"audio/{book_id}/")
    storage.delete_prefix(f"audio-archive/{book_id}/")
    storage.delete_prefix(f"pdfs/{book_id}/")
    for d in (os.path.join("storage", "audio", str(book_id)),
              os.path.join("storage", "audio-archive", str(book_id))):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    if book.pdf_path.startswith("storage/") and os.path.exists(book.pdf_path):
        os.remove(book.pdf_path)
    db.delete(book)
    db.commit()
    return {"ok": True}
