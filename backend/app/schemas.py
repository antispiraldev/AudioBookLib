from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class SegmentOut(BaseModel):
    id: int
    order: int
    status: str
    duration: Optional[float] = None

    model_config = {"from_attributes": True}


class BookOut(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    filename: str
    status: str
    page_count: Optional[int] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    segments: List[SegmentOut] = []

    model_config = {"from_attributes": True}


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None
