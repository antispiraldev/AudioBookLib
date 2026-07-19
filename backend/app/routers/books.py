import logging
import os
import shutil
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, Segment, User
from ..schemas import BookOut, BookUpdate, SegmentText, SegmentUpdate
from ..services import storage, tts
from ..services.suggest import suggest_metadata
from ..tasks import ingest_book, synthesize_book
from .auth import get_current_user, require_admin

log = logging.getLogger(__name__)

router = APIRouter()

STORAGE_PDF = "storage/pdfs"

os.makedirs(STORAGE_PDF, exist_ok=True)


def _is_admin(user: Optional[User]) -> bool:
    return user is not None and user.role == "admin"


@router.get("/", response_model=List[BookOut])
def list_books(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    q = db.query(Book).order_by(Book.created_at.desc())
    if not _is_admin(user):
        q = q.filter(Book.hidden.is_(False))
    return q.all()


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
    return book


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
    return book


def _is_partially_synthesized(book: Book) -> bool:
    """True when some audio exists but not all — i.e. a narration change now
    would splice two voices. Covers an in-flight synthesis and any book stopped
    partway (e.g. errored mid-run with some ready segments)."""
    if book.status == "synthesizing":
        return True
    ready = sum(1 for s in book.segments if s.status == "ready")
    return 0 < ready < len(book.segments)


# Fields that change what the TTS produces; locked while a book is partway
# through synthesis so the audio can't end up half one voice, half another.
_NARRATION_FIELDS = ("tts_narrator", "tts_instructions")


@router.patch("/{book_id}", response_model=BookOut, dependencies=[Depends(require_admin)])
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    incoming = data.model_dump(exclude_none=True)
    narration_change = any(
        f in incoming and incoming[f] != getattr(book, f) for f in _NARRATION_FIELDS
    )
    if narration_change and _is_partially_synthesized(book):
        raise HTTPException(
            409,
            "Can't change the narrator or instructions while this book is partway "
            "through synthesis — it would splice two voices into one book. Let it "
            "finish (or reset it), then change the voice and re-synthesize.",
        )
    for field, value in incoming.items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


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
    synthesize_book.delay(book_id)
    return book


@router.post("/{book_id}/resynthesize", response_model=BookOut, dependencies=[Depends(require_admin)])
def resynthesize_book(book_id: int, db: Session = Depends(get_db)):
    """Re-voice a finished book: archive the current audio, then regenerate every
    segment with the book's currently selected narrator. Keeps the segment text
    (no re-ingest), unlike reprocess. The old take is archived, never deleted, so
    a re-voice never destroys audio you paid for.

    TODO (deferred): tag archives by render signature and restore a matching take
    for free instead of re-synthesizing, so toggling back to a prior voice costs
    nothing. See docs/TODO.md.
    """
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    if book.status != "complete":
        raise HTTPException(
            409,
            "Re-synthesize is for finished books. This one isn't complete yet — "
            "use Synthesize to (re)generate, or Reprocess to rebuild from the PDF.",
        )
    _archive_audio(book_id)
    for seg in book.segments:
        seg.status = "pending"
        seg.audio_path = None
        seg.duration = None
    book.status = "synthesizing"
    db.commit()
    synthesize_book.delay(book_id)
    db.refresh(book)
    return book


def _archive_audio(book_id: int) -> None:
    """Move a book's generated audio aside to audio-archive/ (server-side on R2,
    a local move otherwise) rather than deleting it — resynthesis costs real
    money and R2 storage is cheap, so a paid-for take is never destroyed."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    storage.archive_prefix(f"audio/{book_id}/", f"audio-archive/{book_id}/{ts}/")
    local_audio = os.path.join("storage", "audio", str(book_id))
    if os.path.isdir(local_audio):
        dst = os.path.join("storage", "audio-archive", str(book_id), ts)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(local_audio, dst)


def _clear_generated(book_id: int, db: Session) -> None:
    """Drop a book's segments so ingest can rebuild cleanly, archiving the
    existing audio first (see _archive_audio)."""
    _archive_audio(book_id)
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
    return book


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
