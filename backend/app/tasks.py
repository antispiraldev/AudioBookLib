import logging
import os

from celery import chord, group

from .celery_app import celery
from .database import SessionLocal
from .models import Book, Segment
from .services.clean import llm_clean
from .services.pdf import extract_text_chunks
from .services.tts import synthesize
from .services import storage

log = logging.getLogger(__name__)

STORAGE_AUDIO = "storage/audio"


@celery.task
def ingest_book(book_id: int) -> None:
    """Extract + clean text into segments, then pause at 'review'.

    Synthesis is deliberately NOT started here — an admin reviews the cleaned
    text and approves via POST /books/{id}/synthesize before we spend on TTS.
    """
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        book.status = "processing"
        db.commit()

        with storage.local_pdf(book.pdf_path) as pdf_path:
            page_count, chunks = extract_text_chunks(pdf_path)
        book.page_count = page_count
        for i, text in enumerate(chunks):
            db.add(Segment(book_id=book_id, order=i, text=llm_clean(text)))
        db.commit()

        book.status = "review"
        db.commit()
    except Exception:
        log.exception("Text extraction failed for book %s", book_id)
        _set_error(db, book_id)
    finally:
        db.close()


@celery.task
def synthesize_book(book_id: int) -> None:
    """Retry: reset stuck/errored segments and re-synthesize in parallel."""
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        book.status = "synthesizing"
        # Reset processing segments so the new chord owns them cleanly
        stuck = db.query(Segment).filter(
            Segment.book_id == book_id, Segment.status == "processing"
        ).all()
        for seg in stuck:
            seg.status = "pending"
        db.commit()
        segment_ids = [
            seg.id for seg in
            db.query(Segment)
            .filter(Segment.book_id == book_id, Segment.status != "ready")
            .order_by(Segment.order)
            .all()
        ]
    finally:
        db.close()

    if not segment_ids:
        _finalize_book(book_id)
        return

    chord(
        group(synthesize_segment.s(sid, book_id) for sid in segment_ids)
    )(finalize_book.s(book_id))


@celery.task
def synthesize_segment(segment_id: int, book_id: int) -> str:
    db = SessionLocal()
    try:
        seg = db.get(Segment, segment_id)
        if not seg:
            return "error"
        if seg.status == "ready":
            return "ready"

        book = db.get(Book, book_id)
        instructions = book.tts_instructions if book else None

        local_path = os.path.join(STORAGE_AUDIO, str(book_id), f"{seg.order:04d}.mp3")
        seg.status = "processing"
        db.commit()

        synthesize(seg.text, local_path, instructions=instructions)

        if storage.is_enabled():
            key = f"audio/{book_id}/{seg.order:04d}.mp3"
            storage.upload(local_path, key)
            os.remove(local_path)
            seg.audio_path = key
        else:
            seg.audio_path = local_path

        seg.status = "ready"
        db.commit()
        return "ready"
    except Exception:
        log.exception("TTS failed for segment %s (book %s)", segment_id, book_id)
        try:
            db.rollback()
            seg = db.get(Segment, segment_id)
            if seg:
                seg.status = "error"
                db.commit()
        except Exception:
            pass
        return "error"
    finally:
        db.close()


@celery.task
def finalize_book(results: list, book_id: int) -> None:
    _finalize_book(book_id)


def _finalize_book(book_id: int) -> None:
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        segments = db.query(Segment).filter_by(book_id=book_id).all()
        book.status = "complete" if all(s.status == "ready" for s in segments) else "error"
        db.commit()
    finally:
        db.close()


def _set_error(db, book_id: int) -> None:
    book = db.get(Book, book_id)
    if book:
        book.status = "error"
        db.commit()
