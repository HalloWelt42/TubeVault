"""
TubeVault -  Video Models v1.3.0
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class VideoBase(BaseModel):
    title: str
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    tags: list[str] = []
    notes: Optional[str] = None
    rating: int = Field(default=0, ge=0, le=5)


class VideoCreate(BaseModel):
    url: str
    quality: Optional[str] = None
    format: Optional[str] = None


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    channel_name: Optional[str] = None
    notes: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=0, le=5)
    tags: Optional[list[str]] = None
    category: Optional[str] = None
    category_ids: Optional[list[int]] = None
    video_type: Optional[str] = None
    suggest_override: Optional[str] = None  # null, 'include', 'exclude'


class VideoResponse(VideoBase):
    id: str
    status: str = "pending"
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    thumbnail_path: Optional[str] = None
    download_date: Optional[str] = None
    video_type: str = "video"
    play_count: int = 0
    last_played: Optional[str] = None
    last_position: int = 0
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    videos: list[VideoResponse]
    total: int
    page: int = 1
    per_page: int = 24
    total_pages: int = 1


class VideoInfo(BaseModel):
    """Informationen von YouTube (vor Download)."""
    id: str
    title: str
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    tags: list[str] = []
    streams: list[dict] = []
    captions: list[dict] = []
    already_downloaded: bool = False
