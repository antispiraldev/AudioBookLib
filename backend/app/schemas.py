from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class UserOut(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None
    role: str

    model_config = {"from_attributes": True}


class SegmentOut(BaseModel):
    id: int
    order: int
    status: str
    duration: Optional[float] = None
    chapter_title: Optional[str] = None

    model_config = {"from_attributes": True}


class SegmentText(BaseModel):
    id: int
    order: int
    status: str
    text: str
    chapter_title: Optional[str] = None

    model_config = {"from_attributes": True}


class SegmentUpdate(BaseModel):
    text: str


class BookOut(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    filename: str
    status: str
    hidden: bool = False
    page_count: Optional[int] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None
    tts_instructions: Optional[str] = None
    created_at: datetime
    segments: List[SegmentOut] = []

    model_config = {"from_attributes": True}


class AdminBookRow(BaseModel):
    """One row in the admin books table — lightweight, no segment payloads."""
    id: int
    title: str
    author: Optional[str] = None
    status: str
    genre: Optional[str] = None
    year: Optional[int] = None
    hidden: bool = False
    page_count: Optional[int] = None
    created_at: datetime
    owner_email: Optional[str] = None
    segments_total: int = 0
    segments_ready: int = 0
    segments_error: int = 0


class PipelineEventOut(BaseModel):
    id: int
    book_id: Optional[int] = None
    book_title: Optional[str] = None
    task: str
    level: str
    message: str
    traceback: Optional[str] = None
    created_at: datetime


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None
    hidden: Optional[bool] = None
    tts_instructions: Optional[str] = None
