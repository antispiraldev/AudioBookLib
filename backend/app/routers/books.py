import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import Book, Segment
from ..schemas import BookOut
from ..services.pdf import extract_text_chunks
from ..services.tts import synthesize

router = APIRouter()

STORAGE_PDF = "storage/pdfs"
STORAGE_AUDIO = "storage/audio"

os.makedirs(STORAGE_PDF, exist_ok=True)
os.makedirs(STORAGE_AUDIO, exist_ok=True)


@router.get("/", response_model=List[BookOut])
def list_books(db: Session = Depends(get_db)):
    return db.query(Book).order_by(Book.created_at.desc()).all()


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.post("/", response_model=BookOut)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    safe_name = f"{file.filename}"
    pdf_path = os.path.join(STORAGE_PDF, safe_name)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    book = Book(title=title, author=author, filename=file.filename, pdf_path=pdf_path)
    db.add(book)
    db.commit()
    db.refresh(book)

    background_tasks.add_task(_ingest_and_synthesize, book.id)
    return book


@router.post("/{book_id}/synthesize", response_model=BookOut)
def retry_synthesize(
    book_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    background_tasks.add_task(_synthesize_book, book_id)
    return book


@router.delete("/{book_id}")
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()
    return {"ok": True}


# ── background tasks ──────────────────────────────────────────────────────────

def _ingest_and_synthesize(book_id: int) -> None:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        book.status = "processing"
        db.commit()

        page_count, chunks = extract_text_chunks(book.pdf_path)
        book.page_count = page_count
        for i, text in enumerate(chunks):
            db.add(Segment(book_id=book_id, order=i, text=text))
        db.commit()
    except Exception:
        _set_error(db, book_id)
        db.close()
        return
    finally:
        db.close()

    _synthesize_book(book_id)


def _synthesize_book(book_id: int) -> None:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        book.status = "synthesizing"
        db.commit()

        for seg in db.query(Segment).filter_by(book_id=book_id).order_by(Segment.order).all():
            if seg.status == "ready":
                continue
            audio_path = os.path.join(STORAGE_AUDIO, str(book_id), f"{seg.order:04d}.mp3")
            seg.status = "processing"
            db.commit()
            try:
                synthesize(seg.text, audio_path)
                seg.audio_path = audio_path
                seg.status = "ready"
            except Exception:
                seg.status = "error"
            db.commit()

        segments = db.query(Segment).filter_by(book_id=book_id).all()
        book.status = "complete" if all(s.status == "ready" for s in segments) else "error"
        db.commit()
    except Exception:
        _set_error(db, book_id)
    finally:
        db.close()


def _set_error(db: Session, book_id: int) -> None:
    book = db.get(Book, book_id)
    if book:
        book.status = "error"
        db.commit()
