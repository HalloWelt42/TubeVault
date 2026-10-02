"""
TubeVault – Ladbare Feed-Einträge

Die EINE Definition, welche Einträge eines Kanals noch geladen werden können.
Drip, Auto-Download, der Stapel "fehlende Videos" und die Zähler der
Kanalseite fragen alle hier - vorher hatte jede Stelle ihre eigene Auswahl,
und Stapel wie Prognose griffen immer wieder dieselben nicht ladbaren Videos
(ignoriert, geparkt, fehlgeschlagen, im externen Archiv, Livestream).
"""
from app.database import db
from app.services import video_classifier

# Bedingung auf rss_entries mit dem Alias r
_LOADABLE_SQL = """
    NOT EXISTS (SELECT 1 FROM videos v WHERE v.id = r.video_id AND v.status = 'ready')
    AND NOT EXISTS (SELECT 1 FROM ignored_videos i WHERE i.video_id = r.video_id)
    AND NOT EXISTS (SELECT 1 FROM video_archives va WHERE va.video_id = r.video_id)
    AND NOT EXISTS (
        SELECT 1 FROM jobs j
        WHERE j.type = 'download'
          AND json_extract(j.metadata, '$.video_id') = r.video_id
          AND j.status IN ('queued', 'active', 'retry_wait', 'parked', 'error'))
    AND COALESCE(r.video_type, 'video') <> 'live'
"""


async def clause() -> str:
    """SQL-Bedingung (Alias r) für ladbare Einträge; berücksichtigt, ob Shorts
    ausgeschlossen sind."""
    return _LOADABLE_SQL + await video_classifier.without_shorts("r")


async def is_loadable(video_id: str) -> bool:
    row = await db.fetch_one(
        f"SELECT 1 FROM rss_entries r WHERE r.video_id = ? AND {await clause()} LIMIT 1",
        (video_id,))
    return row is not None


async def count(channel_id: str) -> int:
    return await db.fetch_val(
        f"SELECT COUNT(*) FROM rss_entries r WHERE r.channel_id = ? AND {await clause()}",
        (channel_id,)) or 0
