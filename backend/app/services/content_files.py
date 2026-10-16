"""
TubeVault - Inhalte als Datei (Nutzerentscheidung 16.10.2026)

Inhalte liegen als Datei neben dem Video, die Datenbank ist Index, Suche
und Zustand; aus den Dateien lässt sie sich neu aufbauen (rebuild_service):
  info.json           Metadaten (meta_sidecar)
  description.txt     Beschreibung (text_export)
  chapters.json       Kapitel (text_export)

Beschreibungen schreibt text_export.write_description (Datei, nie Spalte).
write_for() bringt für ein Video die übrigen Dateien auf Stand. Die Schleife
zieht nach, was fehlt, in kleinen Paketen im Hintergrund: Beschreibungen,
die noch in der Spalte stehen, wandern in die Datei (danach ist die Spalte
leer), Kapitel ohne Datei, vorgemerkte Begleitdateien (sidecar_stale).
Früher ging das nur per Knopf in der Verwaltung - wer eine alte Datenbank
mitbringt, musste davon wissen.
"""
import asyncio
import logging

from app.database import db
from app.services import meta_sidecar, text_export

logger = logging.getLogger(__name__)

BATCH = 100
PAUSE_S = 0.2           # zwischen zwei Paketen: Platte und Ereignisschleife behalten Luft
IDLE_S = 600            # nichts zu tun: so lange bis zum nächsten Blick
START_DELAY_S = 120

_IN_COLUMN = "FROM videos v WHERE COALESCE(v.description, '') <> ''"
_CHAPTERS = """FROM (SELECT DISTINCT video_id FROM chapters) c
    WHERE NOT EXISTS (SELECT 1 FROM text_files t WHERE t.video_id = c.video_id AND t.kind = 'chapters')"""


async def write_for(video_id: str) -> None:
    """Inhaltsdateien eines Videos auf Stand bringen: Beschreibung aus der
    Spalte (falls noch dort), Kapitel, info.json (idempotent, wirft nie)."""
    try:
        column = await db.fetch_val("SELECT description FROM videos WHERE id = ?", (video_id,))
        if column:
            await text_export.move_description_from_column(video_id, column)
        await text_export.export_chapters(video_id)
    except Exception as e:
        logger.warning(f"[INHALTE] {video_id}: Textdateien nicht geschrieben: {e}")
    await meta_sidecar.write_sidecar(video_id)


async def remaining() -> int:
    """So viele Dateien fehlen noch (Beschreibungen, Kapitel, vorgemerkte Begleitdateien)."""
    descriptions = await db.fetch_val(f"SELECT COUNT(*) {_IN_COLUMN}") or 0
    chapters = await db.fetch_val(f"SELECT COUNT(*) {_CHAPTERS}") or 0
    stale = await db.fetch_val("SELECT COUNT(*) FROM sidecar_stale") or 0
    return descriptions + chapters + stale


async def _export(ids: list[str], export) -> int:
    written = 0
    for video_id in ids:
        try:
            result = await export(video_id)
            written += bool(result)
        except Exception as e:
            logger.warning(f"[INHALTE] {video_id}: {e}")
    return written


async def _move_descriptions(rows) -> int:
    moved = 0
    for row in rows:
        try:
            moved += await text_export.move_description_from_column(row["id"], row["description"])
        except Exception as e:
            logger.warning(f"[INHALTE] {row['id']}: Beschreibung nicht übertragen: {e}")
    return moved


async def run_batch() -> int:
    """Ein Paket nachziehen; Anzahl geschriebener Dateien (0: nichts zu tun
    oder nur Fehlschläge - dann wartet die Schleife, statt zu kreisen)."""
    descriptions = await db.fetch_all(f"SELECT v.id, v.description {_IN_COLUMN} LIMIT ?", (BATCH,))
    chapters = [r["video_id"] for r in await db.fetch_all(f"SELECT c.video_id {_CHAPTERS} LIMIT ?", (BATCH,))]
    written = await _move_descriptions(descriptions)
    written += await _export(chapters, text_export.export_chapters)
    written += await meta_sidecar.refresh_stale(limit=BATCH)
    return written


async def loop() -> None:
    await asyncio.sleep(START_DELAY_S)
    while True:
        try:
            if await run_batch():
                await asyncio.sleep(PAUSE_S)
                continue
        except Exception as e:
            logger.error(f"[INHALTE] Fehler: {e}", exc_info=True)
        await asyncio.sleep(IDLE_S)
