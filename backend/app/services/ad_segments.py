"""
TubeVault – Werbestellen

Eine Stelle für die Frage "welche Zeitabschnitte eines Videos sind Werbung".
Wiedergabe (überspringen), Transkripte (Sätze darin fallen weg) und Downloads
(werden ohne sie erzeugt) richten sich alle danach. Die Videodatei selbst
bleibt immer vollständig - ändern sich die Marken, gilt sofort der neue Stand.

Herkunft der Marken (Tabelle ad_markers):
    manual          selbst gesetzt, zählt immer als Werbung
    sponsorblock    vom Werbemarken-Dienst der Gemeinschaft (Endpunkt
                    "sponsorblock_api"), nur die Arten in HIDDEN_CATEGORIES

Der Dienst wird mit der Zeit vollständiger: Bei neuen Videos tragen Zuschauer
die Stellen erst nach Stunden oder Tagen ein. Darum wird beim Öffnen eines
Videos nachgefragt, wenn der letzte Abruf alt genug ist (junge Videos öfter,
alte selten), und der Stand des Dienstes ersetzt die bisherigen Marken.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import BaseModel

from app.database import db
from app.services.endpoint_service import get_service_url
from app.services.subtitle_segments import Segment
from app.utils.video_ids import is_source_video

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ad_marker_checks (
    video_id TEXT PRIMARY KEY,
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    found INTEGER NOT NULL DEFAULT 0
);
-- Transkripte, deren Abschnitte ohne die Werbestellen neu gebildet werden
CREATE TABLE IF NOT EXISTS ad_transcript_rebuilds (video_id TEXT PRIMARY KEY);
CREATE TRIGGER IF NOT EXISTS trg_ad_marker_checks_video_delete AFTER DELETE ON videos
BEGIN
    DELETE FROM ad_marker_checks WHERE video_id = old.id;
    DELETE FROM ad_transcript_rebuilds WHERE video_id = old.id;
END;
"""

DEFAULT_API = "https://sponsor.ajay.app"

# Arten, die als Werbung gelten und verschwinden (Entscheidung des Nutzers)
CATEGORY_LABELS = {
    "sponsor": "Bezahlte Werbung",
    "selfpromo": "Eigenwerbung",
    "interaction": "Aufruf zur Interaktion",
    "intro": "Intro",
    "outro": "Outro",
}
HIDDEN_CATEGORIES = tuple(CATEGORY_LABELS)

# Wie oft nachgefragt wird: Videos, die jünger sind als YOUNG_DAYS, alle
# REFRESH_YOUNG_HOURS Stunden; ältere nur noch alle REFRESH_OLD_DAYS Tage
YOUNG_DAYS = 30
REFRESH_YOUNG_HOURS = 6
REFRESH_OLD_DAYS = 30
# So lange darf das Nachfragen das Öffnen eines Videos höchstens aufhalten
REFRESH_WAIT_SECONDS = 4
API_TIMEOUT_SECONDS = 10


class RefreshResult(BaseModel):
    found: int
    changed: bool


async def install_schema(connection, backfill: bool = False) -> None:
    """backfill: einmalig alle vorhandenen Transkripte von Videos mit
    Werbestellen zum Neubilden vormerken (sie entstanden noch mit Werbung)."""
    await connection.executescript(SCHEMA_SQL)
    if backfill:
        await connection.execute(
            """INSERT OR IGNORE INTO ad_transcript_rebuilds (video_id)
               SELECT DISTINCT t.video_id FROM transcripts t
               JOIN ad_markers m ON m.video_id = t.video_id WHERE t.status = 'ok'""")
    await connection.commit()


async def background_rebuild() -> None:
    """Vorgemerkte Transkripte nacheinander neu bilden, dann Ende."""
    while True:
        row = await db.fetch_one("SELECT video_id FROM ad_transcript_rebuilds LIMIT 1")
        if not row:
            return
        try:
            await markers_changed(row["video_id"])
        except Exception as e:
            logger.warning(f"[WERBUNG] Transkript {row['video_id']} nicht neu gebildet: {e}")
        await db.execute("DELETE FROM ad_transcript_rebuilds WHERE video_id = ?", (row["video_id"],))


def has_source(video_id: str) -> bool:
    """Nur Videos der Quelle haben Marken beim Dienst (keine eigenen/importierten)."""
    return is_source_video(video_id)


# ─── Zeitabschnitte ───────────────────────────────────────────────────

def merge(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Überlappende oder aneinanderstoßende Abschnitte zusammenfassen."""
    merged: list[list[float]] = []
    for start, end in sorted(r for r in ranges if r[1] > r[0]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


async def skip_ranges(video_id: str) -> list[tuple[float, float]]:
    """Die Werbestellen eines Videos, zusammengefasst und sortiert."""
    marks = ",".join("?" * len(HIDDEN_CATEGORIES))
    rows = await db.fetch_all(
        f"""SELECT start_time, end_time FROM ad_markers
            WHERE video_id = ? AND (COALESCE(source, 'manual') = 'manual' OR category IN ({marks}))""",
        (video_id, *HIDDEN_CATEGORIES))
    return merge([(row["start_time"], row["end_time"]) for row in rows])


def is_hidden(category: Optional[str], source: Optional[str]) -> bool:
    return (source or "manual") == "manual" or category in HIDDEN_CATEGORIES


def outside(segments: list[Segment], ranges: list[tuple[float, float]]) -> list[Segment]:
    """Sätze ohne die, deren Mitte in einer Werbestelle liegt."""
    def inside(segment: Segment) -> bool:
        middle = (segment.start + segment.end) / 2
        return any(start <= middle < end for start, end in ranges)
    return [segment for segment in segments if not inside(segment)] if ranges else segments


def keep_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    """Die Teile eines Videos, die ohne Werbung übrig bleiben."""
    keep, position = [], 0.0
    for start, end in merge(ranges):
        if start > position:
            keep.append((position, min(start, duration)))
        position = max(position, end)
    if position < duration:
        keep.append((position, duration))
    return [(start, end) for start, end in keep if end - start > 0.05]


# ─── Abgleich mit dem Dienst ──────────────────────────────────────────

async def _fetch(video_id: str) -> list[dict]:
    base = await get_service_url("sponsorblock_api") or DEFAULT_API
    categories = '["' + '","'.join(HIDDEN_CATEGORIES) + '"]'
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{base}/api/skipSegments",
                                    params={"videoID": video_id, "categories": categories})
    if response.status_code == 404:          # der Dienst kennt (noch) keine Stellen
        return []
    response.raise_for_status()
    return [seg for seg in response.json()
            if len(seg.get("segment") or []) == 2 and seg["segment"][1] > seg["segment"][0]]


# Ein Abgleich je Video zur Zeit (Öffnen und Download können zusammenfallen)
_locks: dict[str, asyncio.Lock] = {}


async def refresh(video_id: str) -> RefreshResult:
    """Den Stand des Dienstes übernehmen: er ersetzt die bisherigen Marken aus
    dem Dienst vollständig (auch zurückgezogene verschwinden). Eigene Marken
    bleiben. Hat sich etwas geändert, werden die Transkripte nachgezogen."""
    async with _locks.setdefault(video_id, asyncio.Lock()):
        return await _refresh(video_id)


async def _refresh(video_id: str) -> RefreshResult:
    segments = await _fetch(video_id)
    current = await db.fetch_all(
        """SELECT sb_uuid, start_time, end_time, category FROM ad_markers
           WHERE video_id = ? AND source = 'sponsorblock'""", (video_id,))
    before = {(r["sb_uuid"], r["start_time"], r["end_time"], r["category"]) for r in current}
    after = {(s.get("UUID"), float(s["segment"][0]), float(s["segment"][1]), s.get("category"))
             for s in segments}
    changed = before != after
    if changed:
        await db.execute("DELETE FROM ad_markers WHERE video_id = ? AND source = 'sponsorblock'", (video_id,))
        for seg in segments:
            category = seg.get("category")
            await db.execute(
                """INSERT INTO ad_markers (video_id, start_time, end_time, label, source, category, sb_uuid, votes)
                   VALUES (?, ?, ?, ?, 'sponsorblock', ?, ?, ?)""",
                (video_id, float(seg["segment"][0]), float(seg["segment"][1]),
                 CATEGORY_LABELS.get(category, category), category, seg.get("UUID"), seg.get("votes", 0)))
    await db.execute(
        """INSERT INTO ad_marker_checks (video_id, checked_at, found) VALUES (?, datetime('now'), ?)
           ON CONFLICT(video_id) DO UPDATE SET checked_at = excluded.checked_at, found = excluded.found""",
        (video_id, len(segments)))
    if changed:
        await markers_changed(video_id)
    return RefreshResult(found=len(segments), changed=changed)


async def is_due(video_id: str) -> bool:
    row = await db.fetch_one(
        """SELECT c.checked_at, v.upload_date FROM videos v
           LEFT JOIN ad_marker_checks c ON c.video_id = v.id WHERE v.id = ?""", (video_id,))
    if not row:
        return False
    if not row["checked_at"]:
        return True
    checked = datetime.fromisoformat(row["checked_at"])
    uploaded = (row["upload_date"] or "")[:10]
    young = bool(uploaded) and uploaded >= (datetime.utcnow() - timedelta(days=YOUNG_DAYS)).strftime("%Y-%m-%d")
    interval = timedelta(hours=REFRESH_YOUNG_HOURS) if young else timedelta(days=REFRESH_OLD_DAYS)
    return datetime.utcnow() - checked >= interval


async def refresh_if_due(video_id: str) -> None:
    """Beim Öffnen eines Videos: nachfragen, wenn es Zeit ist. Hält das Öffnen
    höchstens REFRESH_WAIT_SECONDS auf; ist der Dienst nicht erreichbar, gilt
    der bisherige Stand."""
    if not has_source(video_id) or not await is_due(video_id):
        return
    # Abgeschirmt: dauert es länger, läuft der Abgleich zu Ende, statt mitten
    # im Ersetzen der Marken abgebrochen zu werden
    task = asyncio.ensure_future(refresh(video_id))
    task.add_done_callback(lambda t: t.cancelled() or t.exception())   # Fehler gilt als abgeholt
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=REFRESH_WAIT_SECONDS)
    except asyncio.TimeoutError:
        logger.info(f"[WERBUNG] {video_id}: Abgleich dauert länger, läuft im Hintergrund weiter")
    except Exception as e:
        logger.info(f"[WERBUNG] {video_id}: Werbemarken nicht abgeglichen ({e.__class__.__name__}: {e})")


async def markers_changed(video_id: str) -> None:
    """Die Werbestellen eines Videos haben sich geändert: Transkript nachziehen."""
    from app.services import transcripts
    await transcripts.rebuild(video_id)
