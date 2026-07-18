"""Record pipeline events (errors/warnings) to the shared database.

Used from inside Celery tasks on the worker droplet. Deliberately opens its own
session and swallows any failure: recording an event must never mask the
original error or crash the task that is already handling one.
"""
import logging
from typing import Optional

from ..database import SessionLocal
from ..models import PipelineEvent

log = logging.getLogger(__name__)

# Guard against a runaway traceback bloating the row.
_MAX_MESSAGE = 4000
_MAX_TRACEBACK = 16000


def record_pipeline_event(
    book_id: Optional[int],
    task: str,
    level: str,
    message: str,
    traceback: Optional[str] = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            PipelineEvent(
                book_id=book_id,
                task=task,
                level=level,
                message=(message or "")[:_MAX_MESSAGE],
                traceback=traceback[:_MAX_TRACEBACK] if traceback else None,
            )
        )
        db.commit()
    except Exception:
        log.exception("failed to record pipeline event (%s/%s)", task, level)
        db.rollback()
    finally:
        db.close()
