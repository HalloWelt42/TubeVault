"""
TubeVault – Video-Typ bestimmen v1.0.0

Die EINE Stelle, die entscheidet, ob etwas ein Video, ein Short oder ein
Livestream ist.

Früher riet jede Stelle für sich, meist über die Dauer ("bis 60 Sekunden =
Short"). Das ist doppelt falsch: Shorts dürfen bis drei Minuten lang sein,
und ein kurzes normales Video ist kein Short. Ergebnis im Bestand: als
Short geführte Zwei-Stunden-Videos und als Video geführte Shorts.

Regeln:
  1. Livestream: sagt die Quelle selbst (läuft gerade / war ein Livestream).
  2. Short: die Quelle führt das Video unter ihrer Shorts-Adresse oder in
     ihrem Shorts-Reiter. Das allein genügt aber nicht: die Quelle zeigt auch
     alte, kurze, quadratische Videos von 2010 im Shorts-Player und hat sie
     nachträglich in den Shorts-Reiter einsortiert. Deshalb gilt zusätzlich
     (als Datenbankregel, für jeden Schreibweg, siehe SHORT_RULES_SQL):
       - Was vor dem Start von Shorts hochgeladen wurde (SHORTS_START), ist
         kein Short - es kann nicht als Short gemacht worden sein.
       - Kanäle in short_exempt_channels führen nie Shorts (Entscheidung des
         Nutzers, z.B. Kanäle mit kurzen, aber vollwertigen Videos).
  3. Was länger ist als ein Short je sein kann, ist ohne Nachfrage kein Short.
  4. Ist die Quelle nicht erreichbar, bleibt der Typ "ungeprüft" und wird
     später nachgeholt. Geraten wird nicht.

Geprüft-Kennzeichen (type_verified):
    0 = ungeprüft, 1 = von der Quelle bestätigt, 2 = vom Nutzer gesetzt
Ein vom Nutzer gesetzter Typ wird nie überschrieben.
"""
import asyncio
import logging
from typing import Literal, Optional

import httpx

from app.utils import source_net
from pydantic import BaseModel

from app.database import db

logger = logging.getLogger(__name__)

VideoType = Literal["video", "short", "live"]

UNVERIFIED, VERIFIED, MANUAL = 0, 1, 2

SHORT_URL = "https://www.youtube.com/shorts/{video_id}"
# Start von Shorts (erste Veröffentlichung, 14.09.2020). Ältere Uploads
# wurden nicht als Short hochgeladen.
SHORTS_START = "2020-09-14"

# Die Regel greift beim Schreiben, egal von wo (Prüfung, Kanal-Scan, Feed,
# Download). Ein vom Nutzer gesetzter Typ (type_verified 2) bleibt unberührt;
# fehlt das Datum, greift der Stichtag nicht (es wird nicht geraten).
_NOT_A_SHORT_VIDEO = f"""
    COALESCE(new.type_verified, 0) != 2 AND (
        (new.upload_date IS NOT NULL AND substr(new.upload_date, 1, 10) < '{SHORTS_START}')
        OR new.channel_id IN (SELECT channel_id FROM short_exempt_channels))"""
_NOT_A_SHORT_ENTRY = f"""
    COALESCE(new.type_verified, 0) != 2 AND (
        (new.published IS NOT NULL AND substr(new.published, 1, 10) < '{SHORTS_START}')
        OR new.channel_id IN (SELECT channel_id FROM short_exempt_channels))"""
SHORT_RULES_SQL = f"""
CREATE TABLE IF NOT EXISTS short_exempt_channels (
    channel_id TEXT PRIMARY KEY,
    channel_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TRIGGER IF NOT EXISTS trg_short_rule_video_insert AFTER INSERT ON videos
WHEN new.video_type = 'short' AND {_NOT_A_SHORT_VIDEO}
BEGIN UPDATE videos SET video_type = 'video' WHERE id = new.id; END;
CREATE TRIGGER IF NOT EXISTS trg_short_rule_video_update
AFTER UPDATE OF video_type, upload_date, channel_id ON videos
WHEN new.video_type = 'short' AND {_NOT_A_SHORT_VIDEO}
BEGIN UPDATE videos SET video_type = 'video' WHERE id = new.id; END;
CREATE TRIGGER IF NOT EXISTS trg_short_rule_entry_insert AFTER INSERT ON rss_entries
WHEN new.video_type = 'short' AND {_NOT_A_SHORT_ENTRY}
BEGIN UPDATE rss_entries SET video_type = 'video' WHERE id = new.id; END;
CREATE TRIGGER IF NOT EXISTS trg_short_rule_entry_update
AFTER UPDATE OF video_type, published, channel_id ON rss_entries
WHEN new.video_type = 'short' AND {_NOT_A_SHORT_ENTRY}
BEGIN UPDATE rss_entries SET video_type = 'video' WHERE id = new.id; END;
"""


async def install_rules(connection) -> None:
    """Regeltabelle und Trigger anlegen und den Bestand einmal danach richten."""
    await connection.executescript(SHORT_RULES_SQL)
    await connection.execute(
        f"""UPDATE videos SET video_type = 'video'
            WHERE video_type = 'short' AND COALESCE(type_verified, 0) != 2 AND (
                (upload_date IS NOT NULL AND substr(upload_date, 1, 10) < '{SHORTS_START}')
                OR channel_id IN (SELECT channel_id FROM short_exempt_channels))""")
    await connection.execute(
        f"""UPDATE rss_entries SET video_type = 'video'
            WHERE video_type = 'short' AND COALESCE(type_verified, 0) != 2 AND (
                (published IS NOT NULL AND substr(published, 1, 10) < '{SHORTS_START}')
                OR channel_id IN (SELECT channel_id FROM short_exempt_channels))""")
    await connection.commit()


async def exempt_channels() -> list[dict]:
    rows = await db.fetch_all(
        "SELECT channel_id, channel_name, created_at FROM short_exempt_channels ORDER BY channel_name")
    return [dict(r) for r in rows]


async def is_channel_exempt(channel_id: str) -> bool:
    return bool(await db.fetch_val(
        "SELECT 1 FROM short_exempt_channels WHERE channel_id = ?", (channel_id,)))


async def set_channel_exempt(channel_id: str, exempt: bool, channel_name: Optional[str] = None) -> int:
    """Kanal als "führt nie Shorts" markieren oder die Markierung aufheben.
    Beim Markieren werden seine Shorts sofort zu Videos (außer von Hand
    gesetzte); beim Aufheben bleibt alles, wie es ist - nichts wird
    nachträglich wieder zum Short. Liefert die Zahl umgestellter Videos."""
    if not exempt:
        await db.execute("DELETE FROM short_exempt_channels WHERE channel_id = ?", (channel_id,))
        return 0
    name = channel_name or await db.fetch_val(
        "SELECT channel_name FROM videos WHERE channel_id = ? AND channel_name IS NOT NULL LIMIT 1",
        (channel_id,))
    await db.execute(
        "INSERT OR IGNORE INTO short_exempt_channels (channel_id, channel_name) VALUES (?, ?)",
        (channel_id, name))
    cursor = await db.execute(
        """UPDATE videos SET video_type = 'video'
           WHERE channel_id = ? AND video_type = 'short' AND COALESCE(type_verified, 0) != 2""",
        (channel_id,))
    await db.execute(
        """UPDATE rss_entries SET video_type = 'video'
           WHERE channel_id = ? AND video_type = 'short' AND COALESCE(type_verified, 0) != 2""",
        (channel_id,))
    return cursor.rowcount or 0
# Shorts sind höchstens drei Minuten lang; kleine Reserve für Rundungen
SHORT_MAX_SECONDS = 185
_PROBE_TIMEOUT_S = 10
# Ohne Zustimmungs-Cookie leitet die Quelle aus der EU auf eine Einwilligungsseite um
_PROBE_HEADERS = {"Cookie": "SOCS=CAI", "User-Agent": "Mozilla/5.0"}


class Classification(BaseModel):
    video_type: VideoType
    verified: bool


def is_youtube_id(video_id: str) -> bool:
    return len(video_id or "") == 11 and not video_id.startswith("local_")


async def probe_short(video_id: str, client: Optional[httpx.AsyncClient] = None) -> Optional[bool]:
    """Führt die Quelle dieses Video als Short? True / False / None (unklar)."""
    if not is_youtube_id(video_id):
        return False
    own = client is None
    client = client or source_net.async_client(timeout=_PROBE_TIMEOUT_S, follow_redirects=False)
    try:
        response = await client.head(SHORT_URL.format(video_id=video_id), headers=_PROBE_HEADERS)
    except httpx.HTTPError as e:
        logger.debug(f"[TYP] {video_id}: Probe fehlgeschlagen ({e.__class__.__name__})")
        return None
    finally:
        if own:
            await client.aclose()

    if response.status_code == 200:
        return True
    if response.status_code in (301, 302, 303, 307, 308):
        if "/watch" in response.headers.get("location", ""):
            return False
    return None   # Einwilligungsseite, Drosselung, Störung: nicht raten


def live_from_info(info: dict) -> bool:
    """Livestream laut Angaben der Quelle (läuft, lief oder ist angekündigt)."""
    if info.get("is_live") or info.get("was_live"):
        return True
    return info.get("live_status") in ("is_live", "was_live", "post_live", "is_upcoming")


async def classify(video_id: str, *, is_live: bool = False, duration: Optional[int] = None,
                   client: Optional[httpx.AsyncClient] = None) -> Classification:
    """Typ eines Videos bestimmen (siehe Regeln im Kopf)."""
    if is_live:
        return Classification(video_type="live", verified=True)
    if duration and duration > SHORT_MAX_SECONDS:
        return Classification(video_type="video", verified=True)
    short = await probe_short(video_id, client)
    if short is None:
        return Classification(video_type="video", verified=False)
    return Classification(video_type="short" if short else "video", verified=True)


# ─── Bestand nachprüfen ───────────────────────────────────────────────

_PAUSE_BETWEEN_PROBES_S = 1.5
# Rechengrösse für die Restdauer-Anzeige (Pause plus Antwortzeit)
SECONDS_PER_PROBE = _PAUSE_BETWEEN_PROBES_S + 0.5
_PAUSE_AFTER_TROUBLE_S = 1800
_TROUBLE_LIMIT = 5
_IDLE_PAUSE_S = 3600


async def settle_without_probe() -> int:
    """Alles, was zu lang für ein Short ist, ohne Nachfrage als geprüft
    eintragen (und fälschlich als Short Geführtes berichtigen)."""
    changed = 0
    for table, key in (("videos", "id"), ("rss_entries", "video_id")):
        cursor = await db.execute(
            f"""UPDATE {table}
                SET video_type = CASE WHEN video_type = 'short' THEN 'video' ELSE video_type END,
                    type_verified = {VERIFIED}
                WHERE COALESCE(type_verified, 0) = {UNVERIFIED}
                  AND duration > ?
                  AND COALESCE(video_type, 'video') IN ('video', 'short')""",
            (SHORT_MAX_SECONDS,))
        changed += cursor.rowcount
    # Eigene Dateien ohne Quelle: dort gibt es keine Shorts
    cursor = await db.execute(
        f"""UPDATE videos SET video_type = 'video', type_verified = {VERIFIED}
            WHERE COALESCE(type_verified, 0) = {UNVERIFIED} AND (length(id) <> 11 OR id LIKE 'local_%')
              AND COALESCE(video_type, 'video') IN ('video', 'short')""")
    return changed + cursor.rowcount


# Was der Hintergrundlauf nachfragt: alle geladenen Videos und die Feed-Einträge,
# die der Nutzer noch vor sich hat (aktiv oder "später", nicht älter als das
# eingestellte Höchstalter). Der übrige Feed-Katalog (zehntausende alte
# Einträge) wird geprüft, sobald ein Eintrag geladen oder der Kanal neu
# gescannt wird - so bleibt die Zahl der Nachfragen bei der Quelle klein.
_VIDEOS_TODO = (
    f"COALESCE(type_verified, 0) = {UNVERIFIED} AND COALESCE(video_type, 'video') <> 'live' "
    "AND length(id) = 11")
_FEED_TODO = (
    f"COALESCE(type_verified, 0) = {UNVERIFIED} AND COALESCE(video_type, 'video') <> 'live' "
    "AND COALESCE(feed_status, 'active') IN ('active', 'later') "
    "AND published >= date('now', '-' || COALESCE("
    "(SELECT value FROM settings WHERE key = 'rss.max_age_days'), '90') || ' days')")


async def _next_unverified() -> Optional[str]:
    """Nächste ungeprüfte ID: zuerst geladene Videos, dann Feed-Einträge."""
    row = await db.fetch_one(
        f"""SELECT id FROM videos WHERE {_VIDEOS_TODO}
            ORDER BY (video_type = 'short') DESC, created_at DESC LIMIT 1""")
    if row:
        return row["id"]
    row = await db.fetch_one(
        f"SELECT video_id FROM rss_entries WHERE {_FEED_TODO} ORDER BY published DESC LIMIT 1")
    return row["video_id"] if row else None


async def apply(video_id: str, classification: Classification) -> None:
    """Geprüften Typ an Video und Feed-Eintrag schreiben (Nutzerwahl bleibt)."""
    if not classification.verified:
        return
    for table, key in (("videos", "id"), ("rss_entries", "video_id")):
        await db.execute(
            f"""UPDATE {table} SET video_type = ?, type_verified = {VERIFIED}
                WHERE {key} = ? AND COALESCE(type_verified, 0) <> {MANUAL}""",
            (classification.video_type, video_id))


# ─── Shorts global ausschliessen ──────────────────────────────────────

async def shorts_excluded() -> bool:
    """Einstellung "Shorts ausschliessen": Shorts erscheinen nirgends und
    werden nicht automatisch geladen."""
    value = await db.fetch_val("SELECT value FROM settings WHERE key = 'shorts.exclude'")
    return value == "true"


async def without_shorts(alias: str = "") -> str:
    """SQL-Baustein (mit führendem AND) für Abfragen über videos oder
    rss_entries; leer, solange Shorts nicht ausgeschlossen sind."""
    if not await shorts_excluded():
        return ""
    column = f"{alias}.video_type" if alias else "video_type"
    return f" AND COALESCE({column}, 'video') <> 'short'"


async def delete_shorts() -> int:
    """Alle geladenen Videos löschen, die die Quelle als Short bestätigt hat
    (oder der Nutzer so eingeordnet hat). Ungeprüfte bleiben unangetastet."""
    from app.services.metadata_service import metadata_service
    rows = await db.fetch_all(
        f"SELECT id FROM videos WHERE video_type = 'short' AND COALESCE(type_verified, 0) IN ({VERIFIED}, {MANUAL})")
    deleted = 0
    for row in rows:
        if await metadata_service.delete_video(row["id"]):
            deleted += 1
    return deleted


async def shorts_overview() -> dict:
    confirmed = await db.fetch_val(
        f"SELECT COUNT(*) FROM videos WHERE video_type = 'short' AND COALESCE(type_verified, 0) IN ({VERIFIED}, {MANUAL})") or 0
    size = await db.fetch_val(
        f"SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE video_type = 'short' AND COALESCE(type_verified, 0) IN ({VERIFIED}, {MANUAL})") or 0
    return {"excluded": await shorts_excluded(), "confirmed_shorts": confirmed,
            "confirmed_bytes": size, "unverified": await pending()}


VALID_TYPES = ("video", "short", "live")


async def set_manual(video_ids: list[str], video_type: str) -> int:
    """Vom Nutzer gesetzter Typ - gilt für Video und Feed-Einträge und wird
    von keiner automatischen Prüfung mehr überschrieben."""
    if video_type not in VALID_TYPES:
        raise ValueError(f"Ungültiger Typ: {video_type}")
    changed = 0
    for video_id in video_ids:
        cursor = await db.execute(
            f"UPDATE videos SET video_type = ?, type_verified = {MANUAL}, "
            "updated_at = datetime('now') WHERE id = ?", (video_type, video_id))
        feed = await db.execute(
            f"UPDATE rss_entries SET video_type = ?, type_verified = {MANUAL} WHERE video_id = ?",
            (video_type, video_id))
        changed += 1 if (cursor.rowcount or feed.rowcount) else 0
    return changed


async def pending() -> int:
    """Wie viele Einträge der Hintergrundlauf noch bei der Quelle nachfragt."""
    videos = await db.fetch_val(f"SELECT COUNT(*) FROM videos WHERE {_VIDEOS_TODO}") or 0
    entries = await db.fetch_val(f"SELECT COUNT(*) FROM rss_entries WHERE {_FEED_TODO}") or 0
    return videos + entries


async def verify_backlog() -> None:
    """Hintergrundlauf: ungeprüfte Typen gemächlich bei der Quelle nachfragen.
    Bei wiederholt unklarer Auskunft (Drosselung, Netz weg) lange pausieren."""
    await asyncio.sleep(90)   # Start des Servers nicht belasten
    settled = await settle_without_probe()
    if settled:
        logger.info(f"[TYP] {settled} Einträge ohne Nachfrage eingeordnet (zu lang für ein Short)")
    trouble = 0
    async with source_net.async_client(timeout=_PROBE_TIMEOUT_S, follow_redirects=False) as client:
        while True:
            video_id = await _next_unverified()
            if not video_id:
                await asyncio.sleep(_IDLE_PAUSE_S)
                await settle_without_probe()
                continue
            short = await probe_short(video_id, client)
            if short is None:
                trouble += 1
                if trouble >= _TROUBLE_LIMIT:
                    logger.info("[TYP] Quelle antwortet nicht eindeutig - Pause")
                    trouble = 0
                    await asyncio.sleep(_PAUSE_AFTER_TROUBLE_S)
                else:
                    await asyncio.sleep(_PAUSE_BETWEEN_PROBES_S * 4)
                continue
            trouble = 0
            await apply(video_id, Classification(video_type="short" if short else "video", verified=True))
            await asyncio.sleep(_PAUSE_BETWEEN_PROBES_S)
