"""
TubeVault – Gespeicherte Einstellungen lesen

Die eine Stelle, an der Dienste den aktuellen Wert einer Einstellung holen:
gespeicherter Wert, sonst der Standard aus dem Einstellungs-Schema.
"""
from app import settings_schema
from app.database import db


async def get(key: str) -> str:
    """Aktueller Wert, leer gespeichert zählt als nicht gesetzt."""
    value = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
    return value if value not in (None, "") else settings_schema.BY_KEY[key].default


async def is_on(key: str) -> bool:
    """Ein Schalter (kind toggle) steht auf an."""
    return (await get(key)) == "true"
