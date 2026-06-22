from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Segment

router = APIRouter()


@router.get("/{segment_id}")
def stream_audio(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg or not seg.audio_path:
        raise HTTPException(404, "Audio not ready")
    return FileResponse(seg.audio_path, media_type="audio/mpeg")
