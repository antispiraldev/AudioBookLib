import logging
import os

from .celery_app import celery
from .database import SessionLocal
from .models import Book, Segment
from .services.pdf import extract_text_chunks
from .services.tts import synthesize

log = logging.getLogger(__name__)

STORAGE_AUDIO = "storage/audio"


@celery.task
def ingest_and_synthesize(book_id: int) -> None:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        book.status = "processing"
        db.commit()

        page_count, chunks = extract_text_chunks(book.pdf_path)
        book.page_count = page_count
        for i, text in enumerate(chunks):
            db.add(Segment(book_id=book_id, order=i, text=text))
        db.commit()
    except Exception:
        log.exception("Text extraction failed for book %s", book_id)
        _set_error(db, book_id)
        db.close()
        return
    finally:
        db.close()

    _run_synthesis(book_id)


@celery.task
def synthesize_book(book_id: int) -> None:
    _run_synthesis(book_id)


def _run_synthesis(book_id: int) -> None:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        book.status = "synthesizing"
        db.commit()

        for seg in db.query(Segment).filter_by(book_id=book_id).order_by(Segment.order).all():
            db.expire(seg)
            db.expire(book)
            if not db.get(Book, book_id):
                return
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
                log.exception("TTS failed for segment %s (book %s)", seg.order, book_id)
                seg.status = "error"
            db.commit()

        book = db.get(Book, book_id)
        if not book:
            return
        segments = db.query(Segment).filter_by(book_id=book_id).all()
        book.status = "complete" if all(s.status == "ready" for s in segments) else "error"
        db.commit()
    except Exception:
        log.exception("Synthesis failed for book %s", book_id)
        _set_error(db, book_id)
    finally:
        db.close()


def _set_error(db, book_id: int) -> None:
    book = db.get(Book, book_id)
    if book:
        book.status = "error"
        db.commit()
