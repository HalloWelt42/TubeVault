"""
TubeVault – Drip: den Bestand nach und nach laden

Kanäle und Playlists geben ihre noch nicht geladenen Videos gestaffelt in die
Warteschlange: je Lauf drip_count Videos, ein Lauf am Tag im nächtlichen
Zeitfenster (next_drip_run). Ist nichts mehr ladbar, schaltet sich der Drip
ab (drip_completed_at). Alles geht als Automatik in die Warteschlange
(origin auto): Gelöschtes bleibt gesperrt. Was ladbar ist, sagt loadable.

Auswahl je Lauf:
  Kanal     das neueste fehlende plus die ältesten fehlenden
  Playlist  die nächsten fehlenden in der Reihenfolge der Playlist
"""
import logging

from app.database import db
from app.services import loadable
from app.utils.file_utils import next_drip_run

logger = logging.getLogger(__name__)

PLAYLIST_DRIP_COUNTS = (1, 3, 5, 10, 20, 50)


async def run_due() -> None:
    """Alle fälligen Kanäle und Playlists einmal bedienen."""
    channels = await db.fetch_all(
        """SELECT id, channel_id, channel_name, drip_count FROM subscriptions
           WHERE drip_enabled = 1 AND enabled = 1
             AND drip_next_run IS NOT NULL AND drip_next_run <= datetime('now')""")
    for sub in channels:
        await _serve("subscriptions", sub["id"], sub["channel_name"], await _channel_picks(sub))
    playlists = await db.fetch_all(
        """SELECT id, name, drip_count FROM playlists
           WHERE drip_enabled = 1 AND drip_next_run IS NOT NULL AND drip_next_run <= datetime('now')""")
    for pl in playlists:
        await _serve("playlists", pl["id"], pl["name"], await pending(pl["id"], pl["drip_count"] or 3))


async def _channel_picks(sub) -> list[str]:
    condition = await loadable.clause()
    count = sub["drip_count"] or 3
    # Das neueste fehlende plus die ältesten fehlenden (bei 1 nur das neueste)
    oldest = [r["video_id"] for r in await db.fetch_all(
        f"""SELECT r.video_id FROM rss_entries r WHERE r.channel_id = ? AND {condition}
            ORDER BY r.published ASC, r.id ASC LIMIT ?""", (sub["channel_id"], max(0, count - 1)))] if count > 1 else []
    marks = ",".join("?" * len(oldest))
    newest = [r["video_id"] for r in await db.fetch_all(
        f"""SELECT r.video_id FROM rss_entries r WHERE r.channel_id = ? AND {condition}
            {f"AND r.video_id NOT IN ({marks})" if oldest else ""}
            ORDER BY r.published DESC, r.id DESC LIMIT 1""", (sub["channel_id"], *oldest))]
    return oldest + newest


async def pending(playlist_id: int, limit: int | None = None) -> list[str]:
    """Noch nicht geladene, ladbare Videos einer Playlist in ihrer Reihenfolge."""
    rows = await db.fetch_all(
        f"""SELECT pv.video_id FROM playlist_videos pv
            WHERE pv.playlist_id = ? AND {loadable.condition("pv.video_id")}
            ORDER BY pv.position, pv.rowid {"LIMIT ?" if limit else ""}""",
        (playlist_id, limit) if limit else (playlist_id,))
    return [r["video_id"] for r in rows]


async def queue(video_ids: list[str], origin: str = "auto") -> int:
    """Videos einreihen; liefert, wie viele angenommen wurden."""
    from app.services.download_service import download_service
    queued = 0
    for video_id in video_ids:
        try:
            await download_service.add_to_queue(url=f"https://www.youtube.com/watch?v={video_id}", origin=origin)
            queued += 1
        except Exception as e:
            logger.warning(f"[DRIP] {video_id} nicht eingereiht: {e}")
    return queued


async def _serve(table: str, row_id: int, name: str, video_ids: list[str]) -> None:
    if not video_ids:
        await db.execute(
            f"""UPDATE {table} SET drip_enabled = 0, drip_completed_at = datetime('now'), drip_next_run = NULL
                WHERE id = ?""", (row_id,))
        logger.info(f"[DRIP] {name}: komplett, Drip abgeschaltet")
        return
    queued = await queue(video_ids)
    next_run = next_drip_run()
    await db.execute(f"UPDATE {table} SET drip_next_run = ? WHERE id = ?", (next_run, row_id))
    logger.info(f"[DRIP] {name}: {queued} Videos eingereiht, nächster Lauf {next_run}")
