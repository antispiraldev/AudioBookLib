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


@router.patch("/{book_id}", response_model=BookOut, dependencies=[Depends(require_admin)])
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    for field, value in data.model_dump(exclude_none=True).items():
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
