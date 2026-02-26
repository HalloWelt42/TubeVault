"""
TubeVault -  Kategorie & Einstellungen Models v1.0.0
© HalloWelt42 -  Private Nutzung
"""

from pydantic import BaseModel
from typing import Optional


# --- Kategorien ---

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: str = "folder"
    parent_id: Optional[int] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: str = "folder"
    parent_id: Optional[int] = None
    sort_order: int = 0
    video_count: int = 0
    children: list["CategoryResponse"] = []


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
