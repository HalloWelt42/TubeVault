"""
TubeVault – Stream Models v1.0.0
© HalloWelt42 – Private Nutzung
"""

from pydantic import BaseModel
from typing import Optional


class StreamInfo(BaseModel):
    id: Optional[int] = None
    video_id: str
    stream_type: str  # 'video', 'audio'
    itag: Optional[int] = None
    mime_type: Optional[str] = None
    quality: Optional[str] = None
    codec: Optional[str] = None
    language: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    fps: Optional[float] = None
    resolution: Optional[str] = None
    is_default: bool = False
    is_combined: bool = False
    downloaded: bool = False


class StreamCombination(BaseModel):
    id: Optional[int] = None
    video_id: str
    name: Optional[str] = None
    video_stream_id: Optional[int] = None
    audio_stream_id: Optional[int] = None
    audio_offset_ms: int = 0
    is_default: bool = False


class StreamCombinationCreate(BaseModel):
    name: str
    video_stream_id: int
    audio_stream_id: int
    audio_offset_ms: int = 0
    is_default: bool = False
