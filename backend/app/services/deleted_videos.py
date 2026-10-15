"""
TubeVault – Gelöschte Videos

Wer ein Video löscht, gibt die Datei auf, nicht das Wissen darüber. Gilt für
jedes Löschen (einzeln, beim Aufräumen, Shorts, mit dem Kanal), Wunsch
15.10.2026:

- Die Angaben des Videos bleiben hier erhalten: die ganze Zeile aus videos
  (Titel, Kanal, Beschreibung, Bewertung, Notizen, Wiedergaben, Musik ...).
  Die Bibliothek (videos) enthält weiter nur, was wirklich da ist.
- Das Video kommt auf die Ignorierliste (ignored_videos, die eine Sperre
  für alles Automatische): Auto-Download und Drip holen es nie von selbst
  zurück. Nur ein ausdrücklich gewählter Download lädt es erneut
  (download_service.add_to_queue hebt die Sperre dann auf).
- Kommt es so zurück, erhält es die eigenen Angaben des Nutzers wieder
  (restore), und der Eintrag hier entfällt.
"""
import json

from app.database import db

MANUALLY_DELETED = "manuell gelöscht"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deleted_videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT,
    channel_name TEXT,
    title TEXT,
    duration INTEGER,
    deleted_at TEXT DEFAULT (datetime('now')),
    data TEXT NOT NULL                -- die ganze Zeile aus videos als JSON
);
CREATE INDEX IF NOT EXISTS idx_deleted_videos_channel ON deleted_videos(channel_id);
"""

# Was der Nutzer selbst gepflegt hat; alles andere liefert die Quelle neu
USER_FIELDS = ("rating", "play_count", "last_played", "last_position", "notes",
               "suggest_override", "music_artist", "music_title", "music_album")


def is_deleted_sql(column: str) -> str:
    """SQL-Ausdruck (1/0) für Abfragen: Hat der Nutzer das Video mit der
    Kennung in column gelöscht? Gilt auch für Löschungen vor diesem Merker."""
    return f"EXISTS (SELECT 1 FROM ignored_videos i WHERE i.video_id = {column} AND i.reason = '{MANUALLY_DELETED}')"


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


async def remember(video: dict) -> None:
    """Vor dem Löschen aufrufen: Angaben sichern und für Automatisches sperren."""
    await db.execute(
        """INSERT OR REPLACE INTO deleted_videos (video_id, channel_id, channel_name, title, duration, data)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video["id"], video.get("channel_id"), video.get("channel_name"), video.get("title"),
         video.get("duration"), json.dumps(video, ensure_ascii=False, default=str)))
    await db.execute(
        "INSERT OR REPLACE INTO ignored_videos (video_id, channel_id, reason) VALUES (?, ?, ?)",
        (video["id"], video.get("channel_id"), MANUALLY_DELETED))


async def restore(video_id: str) -> bool:
    """Nach erneutem Laden: die eigenen Angaben des Nutzers zurückholen.
    Liefert True, wenn es etwas zurückzuholen gab."""
    from app.services import music_flag
    row = await db.fetch_one("SELECT data FROM deleted_videos WHERE video_id = ?", (video_id,))
    if not row:
        return False
    kept = json.loads(row["data"])
    fields = {name: kept[name] for name in USER_FIELDS if kept.get(name) not in (None, "", 0)}
    if fields:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        await db.execute(f"UPDATE videos SET {assignments} WHERE id = ?", (*fields.values(), video_id))
    if kept.get("music_source") == music_flag.USER:
        await music_flag.set_by_user([video_id], bool(kept.get("is_music")))
    await db.execute("DELETE FROM deleted_videos WHERE video_id = ?", (video_id,))
    return True
