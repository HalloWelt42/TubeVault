"""
TubeVault – Settings Router v1.0.0
© HalloWelt42 – Private Nutzung
"""

from fastapi import APIRouter, HTTPException
from app.models.category import SettingUpdate, SettingResponse, SettingsGroupResponse
from app.database import db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Einstellungen"])


@router.get("")
async def get_all_settings():
    """Alle Einstellungen abrufen, gruppiert nach Kategorie."""
    rows = await db.fetch_all(
        "SELECT key, value, description, category FROM settings ORDER BY category, key"
    )
    groups = {}
    for r in rows:
        cat = r["category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(dict(r))
    return [{"category": k, "settings": v} for k, v in groups.items()]


@router.get("/{key}")
async def get_setting(key: str):
    """Einzelne Einstellung abrufen."""
    row = await db.fetch_one("SELECT * FROM settings WHERE key = ?", (key,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Einstellung '{key}' nicht gefunden")
    return dict(row)


@router.put("/{key}")
async def update_setting(key: str, update: SettingUpdate):
    """Einstellung aktualisieren."""
    existing = await db.fetch_one("SELECT key FROM settings WHERE key = ?", (key,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Einstellung '{key}' nicht gefunden")

    await db.execute(
        "UPDATE settings SET value = ? WHERE key = ?",
        (update.value, key)
    )
    return {"key": key, "value": update.value, "updated": True}


@router.post("/reset")
async def reset_settings():
    """Alle Einstellungen auf Standardwerte zurücksetzen."""
    from app.database import DEFAULT_SETTINGS
    for key, value, desc, cat in DEFAULT_SETTINGS:
        await db.execute(
            "UPDATE settings SET value = ? WHERE key = ?",
            (value, key)
        )
    return {"message": "Einstellungen zurückgesetzt"}


# ─── (Shorts Deep-Scan + Reclassify entfernt v1.6.21) ───

