"""
TubeVault -  Download Models v1.3.0
© HalloWelt42 -  Private Nutzung
"""

from pydantic import BaseModel
from typing import Optional


class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = None  # best, 1080p, 720p, 480p, 360p, audio_only
    format: Optional[str] = None   # mp4, webm
    audio_only: bool = False       # True → pytubefix get_audio_only() direkt
    merge_audio: bool = True       # Adaptiv-Video + Audio per FFmpeg mergen
    download_thumbnail: bool = True
    download_subtitles: bool = False
    subtitle_lang: str = "de"
    priority: int = 0              # 0=Queue, 10=Sofort
    itag: Optional[int] = None     # Spezifischer Video-Stream per itag
    audio_itag: Optional[int] = None  # Spezifischer Audio-Stream per itag


class DownloadBatchRequest(BaseModel):
    urls: list[str]
    quality: Optional[str] = None
    audio_only: bool = False


class DownloadResponse(BaseModel):
    id: int
    video_id: Optional[str] = None
    url: str
    priority: int = 0
    status: str = "queued"
    error_message: Optional[str] = None
    progress: float = 0.0
    download_options: dict = {}
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DownloadQueueResponse(BaseModel):
    queue: list[DownloadResponse]
    active_count: int
    queued_count: int
    completed_count: int
    error_count: int


class DownloadProgress(BaseModel):
    """WebSocket Nachricht für Echtzeit-Updates."""
    queue_id: int
    video_id: Optional[str] = None
    title: Optional[str] = None
    status: str
    progress: float
    stage: Optional[str] = None
    stage_label: Optional[str] = None
    speed: Optional[str] = None
    eta: Optional[str] = None
    error: Optional[str] = None
