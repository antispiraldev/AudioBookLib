import logging
import os

from celery import chord, group

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

        segment_ids = [
            seg.id for seg in
            db.query(Segment).filter_by(book_id=book_id).order_by(Segment.order).all()
        ]
        book.status = "synthesizing"
        db.commit()
    except Exception:
        log.exception("Text extraction failed for book %s", book_id)
        _set_error(db, book_id)
        db.close()
        return
    finally:
        db.close()

    chord(
        group(synthesize_segment.s(sid, book_id) for sid in segment_ids)
    )(finalize_book.s(book_id))


@celery.task
def synthesize_book(book_id: int) -> None:
    """Retry: re-synthesize all non-ready segments in parallel."""
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if not book:
            return
        book.status = "synthesizing"
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

        audio_path = os.path.join(STORAGE_AUDIO, str(book_id), f"{seg.order:04d}.mp3")
        seg.status = "processing"
        db.commit()

        synthesize(seg.text, audio_path)
        seg.audio_path = audio_path
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
