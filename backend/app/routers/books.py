import logging
import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, Segment
from ..schemas import BookOut, BookUpdate
from ..services.suggest import suggest_metadata
from ..tasks import ingest_and_synthesize, synthesize_book

log = logging.getLogger(__name__)

router = APIRouter()

STORAGE_PDF = "storage/pdfs"

os.makedirs(STORAGE_PDF, exist_ok=True)


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
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    pdf_path = os.path.join(STORAGE_PDF, file.filename)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    book = Book(title=title, author=author, filename=file.filename, pdf_path=pdf_path)
    db.add(book)
    db.commit()
    db.refresh(book)

    ingest_and_synthesize.delay(book.id)
    return book


@router.patch("/{book_id}", response_model=BookOut)
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


@router.get("/{book_id}/suggest")
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
        return suggest_metadata(book.pdf_path, book.title, excerpt)
    except Exception as e:
        log.exception("suggest_metadata failed for book %d", book_id)
        raise HTTPException(502, f"Suggestion failed: {e}")


@router.post("/{book_id}/synthesize", response_model=BookOut)
def retry_synthesize(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    synthesize_book.delay(book_id)
    return book


@router.delete("/{book_id}")
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()
    return {"ok": True}
