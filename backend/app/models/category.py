"""
TubeVault – Favoriten, Einstellungen und System Models v1.0.0
(Die Kategorien stehen in app.models.categories.)
© HalloWelt42 – Private Nutzung
"""

from pydantic import BaseModel
from typing import Optional


# --- Favoriten ---

class FavoriteCreate(BaseModel):
    video_id: str
    list_name: str = "Standard"


class FavoriteResponse(BaseModel):
    id: int
    video_id: str
    list_name: str
    position: int
    added_at: str


class FavoriteListResponse(BaseModel):
    name: str
    count: int


# --- Einstellungen ---

class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    category: str = "general"


class SettingsGroupResponse(BaseModel):
    category: str
    settings: list[SettingResponse]


# --- System ---

class SystemStats(BaseModel):
    version: str
    video_count: int
    total_size_bytes: int
    total_size_human: str
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
    disk_usage_percent: float
    download_queue_active: int
    download_queue_pending: int
    db_size_bytes: int
    streams_count: int
    categories_count: int
    favorites_count: int
