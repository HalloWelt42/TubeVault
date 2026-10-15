"""
TubeVault - Ladbare Videos

Die EINE Definition, welche Videos noch geladen werden können: nicht schon
geladen, nicht gesperrt (gelöscht, dauerhaft nicht verfügbar), nicht im
externen Archiv, nicht schon in der Warteschlange oder dort gescheitert.
Drip (Kanäle und Playlists), Auto-Download, der Stapel "fehlende Videos" und
die Zähler fragen alle hier - vorher hatte jede Stelle ihre eigene Auswahl,
und Stapel wie Prognose griffen immer wieder dieselben nicht ladbaren Videos.
"""
from app.database import db
from app.services import video_classifier


def condition(video_id_column: str) -> str:
    """SQL-Bedingung für ein Video, dessen Kennung in video_id_column steht."""
    c = video_id_column
    return f"""
    NOT EXISTS (SELECT 1 FROM videos lv WHERE lv.id = {c} AND lv.status = 'ready')
    AND NOT EXISTS (SELECT 1 FROM ignored_videos li WHERE li.video_id = {c})
    AND NOT EXISTS (SELECT 1 FROM video_archives lva WHERE lva.video_id = {c})
    AND NOT EXISTS (
        SELECT 1 FROM jobs lj
        WHERE lj.type = 'download'
          AND json_extract(lj.metadata, '$.video_id') = {c}
          AND lj.status IN ('queued', 'active', 'retry_wait', 'parked', 'error'))
"""


async def clause() -> str:
    """SQL-Bedingung (Alias r) für ladbare Feed-Einträge: ohne Livestreams,
    ohne Shorts, wenn sie ausgeschlossen sind."""
    return (condition("r.video_id") + " AND COALESCE(r.video_type, 'video') <> 'live'"
            + await video_classifier.without_shorts("r"))


async def is_loadable(video_id: str) -> bool:
    row = await db.fetch_one(
        f"SELECT 1 FROM rss_entries r WHERE r.video_id = ? AND {await clause()} LIMIT 1",
        (video_id,))
    return row is not None


async def count(channel_id: str) -> int:
    return await db.fetch_val(
        f"SELECT COUNT(*) FROM rss_entries r WHERE r.channel_id = ? AND {await clause()}",
        (channel_id,)) or 0
