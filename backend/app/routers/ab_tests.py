"""Viewer-side A/B test endpoints.

Everything here is gated by `require_ab_access` (admin OR the per-user
`ab_test_access` grant), so the clips themselves stay private to permitted
listeners. Admin-side management (create/delete/results, granting access) lives
in routers/admin.py.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ABTest, ABTestOption, ABTestVote, User
from ..schemas import ABTestVoteIn
from ..services import storage
from .auth import require_ab_access

router = APIRouter()

# Choices a vote may carry beyond the option keys.
NO_DIFF = "no_diff"


def _option_url(option: ABTestOption) -> str | None:
    """Public URL the frontend plays. None when no clip has been uploaded yet."""
    if not option.audio_key:
        return None
    return f"/api/ab-tests/audio/{option.id}"


def serialize_test(test: ABTest, my_vote: str | None) -> dict:
    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "created_at": test.created_at,
        "options": [
            {
                "id": o.id,
                "key": o.key,
                "label": o.label,
                "audio_url": _option_url(o),
            }
            for o in test.options
        ],
        "my_vote": my_vote,
    }


@router.get("/")
def list_tests(
    db: Session = Depends(get_db), user: User = Depends(require_ab_access)
):
    """Every published test, newest first, with the current user's own vote."""
    tests = (
        db.query(ABTest)
        .filter(ABTest.published.is_(True))
        .order_by(ABTest.created_at.desc())
        .all()
    )
    votes = {
        v.ab_test_id: v.choice
        for v in db.query(ABTestVote).filter(ABTestVote.user_id == user.id).all()
    }
    return [serialize_test(t, votes.get(t.id)) for t in tests]


@router.post("/{test_id}/vote")
def vote(
    test_id: int,
    body: ABTestVoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_ab_access),
):
    """Record (or change) this user's preference on a test."""
    test = db.get(ABTest, test_id)
    if not test or not test.published:
        raise HTTPException(404, "Test not found")

    valid = {o.key for o in test.options} | {NO_DIFF}
    if body.choice not in valid:
        raise HTTPException(400, "Invalid choice")

    existing = (
        db.query(ABTestVote)
        .filter(ABTestVote.ab_test_id == test_id, ABTestVote.user_id == user.id)
        .first()
    )
    if existing:
        existing.choice = body.choice
    else:
        db.add(
            ABTestVote(ab_test_id=test_id, user_id=user.id, choice=body.choice)
        )
    db.commit()
    return {"choice": body.choice}


@router.get("/audio/{option_id}")
def stream_option_audio(
    option_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_ab_access),
):
    """Serve a clip — presigned R2 redirect in prod, local file otherwise."""
    option = db.get(ABTestOption, option_id)
    if not option or not option.audio_key:
        raise HTTPException(404, "Clip not available")

    if storage.is_r2_key(option.audio_key):
        return RedirectResponse(
            storage.presigned_url(option.audio_key, expiry=3600), status_code=302
        )

    if not os.path.exists(option.audio_key):
        raise HTTPException(404, "Clip not available")
    # FileResponse handles Range requests, so seeking in the player works.
    return FileResponse(option.audio_key, media_type="audio/mpeg")
