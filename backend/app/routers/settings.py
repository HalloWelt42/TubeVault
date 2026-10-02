"""
TubeVault – Settings Router v2.0.0
Welche Einstellungen es gibt, ihre Grenzen und Standardwerte stehen im
Einstellungs-Schema (app/settings_schema.py). Dieser Router liest, prüft und
speichert nur.
© HalloWelt42 – Private Nutzung
"""

import logging

from fastapi import APIRouter, HTTPException

from app import settings_schema
from app.database import db
from app.models.category import SettingUpdate

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
        groups.setdefault(r["category"], []).append(dict(r))
    return [{"category": k, "settings": v} for k, v in groups.items()]


@router.get("/schema")
async def get_settings_schema():
    """Beschreibung aller veränderbaren Einstellungen (Art, Grenzen, Auswahl,
    Standardwert). Die Oberfläche baut ihre Regler daraus."""
    return [d.model_dump() for d in settings_schema.SETTINGS]


@router.get("/{key}")
async def get_setting(key: str):
    """Einzelne Einstellung abrufen."""
    row = await db.fetch_one("SELECT * FROM settings WHERE key = ?", (key,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Einstellung '{key}' nicht gefunden")
    return dict(row)


@router.put("/{key}")
async def update_setting(key: str, update: SettingUpdate):
    """Einstellung prüfen und speichern."""
    try:
        value = settings_schema.validate(key, update.value)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Einstellung '{key}' nicht gefunden")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    definition = settings_schema.BY_KEY[key]
    await db.execute(
        """INSERT INTO settings (key, value, description, category) VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value, definition.description or definition.label, definition.category),
    )
    await _notify_services(key)
    return {"key": key, "value": value, "updated": True}


@router.post("/reset")
async def reset_settings():
    """Alle Einstellungen auf Standardwerte zurücksetzen."""
    for definition in settings_schema.SETTINGS:
        await db.execute(
            "UPDATE settings SET value = ? WHERE key = ?", (definition.default, definition.key))
    for definition in settings_schema.SETTINGS:
        await _notify_services(definition.key)
    return {"message": "Einstellungen zurückgesetzt"}


async def _notify_services(key: str) -> None:
    """Dienste, die einen Wert zwischengespeichert halten, neu lesen lassen."""
    if key == "download.cooldown_base_s":
        from app.services.download_service import download_service
        await download_service.reload_cooldown_base()
