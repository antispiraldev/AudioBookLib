import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Segment

router = APIRouter()

CHUNK = 1024 * 64  # 64 KB


@router.get("/{segment_id}")
def stream_audio(segment_id: int, request: Request, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg or not seg.audio_path:
        raise HTTPException(404, "Audio not ready")

    path = seg.audio_path
    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "audio/mpeg",
    }

    if range_header:
        # Parse "bytes=start-end"
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0])
        end = int(byte_range[1]) if byte_range[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_file():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    data = f.read(min(CHUNK, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(length)
        return StreamingResponse(iter_file(), status_code=206, headers=headers)

    # Full file
    def iter_full():
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(iter_full(), status_code=200, headers=headers)
