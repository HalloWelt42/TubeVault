"""
TubeVault – Text-Export Service v1.3.0

Lagert dokument-artige Daten aus der DB in Dateien aus und hält eine
Referenz-Registry in der text_files-Tabelle. Die Datei ist die Wahrheit,
die DB nur Index (Regel R1 in ARCHITECTURE.md).

Paths kommen komplett aus storage.Storage – keine direkten Config-Konstanten
mehr. Von außen umkonfigurierbar per TUBEVAULT_TEXTS_ROOT-ENV.

Struktur – konsistent zum existierenden lyrics_service:
    <texts_root>/<video_id>/<kind>.<ext>

Unterstützte Kinds:
- description  →  description.txt   (Freitext aus videos.description)
- chapters     →  chapters.json     (JSON-Array aus chapters-Tabelle)
"""
import asyncio
import hashlib
import json
import logging

from app.database import db
from app.services.storage import storage

logger = logging.getLogger(__name__)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# Öffentliches Legacy-Attribut für Tests (deprecated, wird später entfernt)
TEXTS_DIR = None  # wird via monkeypatch gesetzt – sonst storage.texts_root


def _resolve_video_dir(video_id: str):
    """Ordner für ein Video. Respektiert Test-Override via TEXTS_DIR."""
    import app.services.text_export as _self
    override = _self.TEXTS_DIR
    if override is not None:
        return override / video_id
    return storage.video_dir(video_id)


def _resolve_text_file(video_id: str, kind: str):
    """Pfad zur Text-Datei. Respektiert Test-Override."""
    import app.services.text_export as _self
    override = _self.TEXTS_DIR
    if override is not None:
        rel = storage.relative_text_path(video_id, kind)
        return override / rel
    return storage.text_file(video_id, kind)


# ═══════════════════════════════════════════════════════════════
# Generischer Kern – Idempotenter Schreib-Pfad
# ═══════════════════════════════════════════════════════════════

async def _write_text_file(video_id: str, kind: str, content: str) -> dict:
    """Schreibt content als Datei und registriert sie in text_files.
    Idempotent: identischer sha256-Hash → kein Write."""
    target = _resolve_text_file(video_id, kind)
    new_hash = _sha256(content)
    rel_name = storage.relative_text_path(video_id, kind)

    existing = await db.fetch_one(
        "SELECT sha256 FROM text_files WHERE video_id=? AND kind=?",
        (video_id, kind),
    )
    if existing and existing["sha256"] == new_hash and target.exists():
        return {
            "filename": rel_name,
            "size": target.stat().st_size,
            "sha256": new_hash,
            "skipped": True,
        }

    def _write() -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target.stat().st_size

    # Datei-I/O nie auf der Ereignisschleife (Nachziehen schreibt tausende)
    size = await asyncio.to_thread(_write)
    await db.execute(
        """INSERT OR REPLACE INTO text_files
           (video_id, kind, filename, size_bytes, sha256, synced_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (video_id, kind, rel_name, size, new_hash),
    )
    await _note_search_change(video_id, kind)
    return {
        "filename": rel_name,
        "size": size,
        "sha256": new_hash,
        "skipped": False,
    }


async def _note_search_change(video_id: str, kind: str) -> None:
    """Die Beschreibungsdatei ist die Wahrheit für Suchindex und Bedeutungssuche:
    nach jeder Änderung das Video für beide zum Nachziehen vormerken (die
    Auslöser auf der Spalte greifen nicht, wenn nur die Datei sich ändert)."""
    if kind != "description":
        return
    from app.services import search_index, semantic_index
    await search_index.mark_dirty(video_id)
    await semantic_index.mark_dirty(video_id)


async def _delete_text_file(video_id: str, kind: str) -> bool:
    """Entfernt Datei + Registry-Eintrag. Nicht-reversibel außer via
    erneutem Export. Returns True wenn die Datei tatsächlich gelöscht wurde."""
    deleted = False
    p = _resolve_text_file(video_id, kind)
    if p.exists():
        try:
            p.unlink()
            deleted = True
        except Exception as e:
            logger.warning(f"[text_export] unlink failed for {video_id} {kind}: {e}")
    await db.execute(
        "DELETE FROM text_files WHERE video_id=? AND kind=?",
        (video_id, kind),
    )
    await _note_search_change(video_id, kind)
    # Ordner aufräumen wenn leer (lässt andere Kinds-Files unberührt)
    try:
        d = _resolve_video_dir(video_id)
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
    except Exception:
        pass
    return deleted


# ═══════════════════════════════════════════════════════════════
# Description (Phase 3a)
# ═══════════════════════════════════════════════════════════════

async def export_description(video_id: str) -> dict | None:
    """Schreibt videos.description als Datei. Idempotent via sha256."""
    row = await db.fetch_one(
        "SELECT description FROM videos WHERE id = ?", (video_id,)
    )
    if not row:
        return None
    content = (row["description"] or "").strip()
    if not content:
        return None
    return await _write_text_file(video_id, "description", content)


# ═══════════════════════════════════════════════════════════════
# Chapters (Phase 3b)
# ═══════════════════════════════════════════════════════════════

async def export_chapters(video_id: str) -> dict | None:
    """Schreibt chapters als JSON-Array-Datei. Format:
    [{"title": ..., "start_time": ..., "end_time": ..., "source": ...}, ...]
    sortiert nach start_time. thumbnail_url wird NICHT persistiert –
    das ist Implementation-Detail (deterministische URL, DB als Cache).
    Idempotent via sha256."""
    rows = await db.fetch_all(
        """SELECT title, start_time, end_time, source
           FROM chapters WHERE video_id = ? ORDER BY start_time""",
        (video_id,),
    )
    if not rows:
        return None
    data = [
        {
            "title": r["title"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "source": r["source"],
        }
        for r in rows
    ]
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return await _write_text_file(video_id, "chapters", content)


async def delete_chapters_export(video_id: str) -> bool:
    return await _delete_text_file(video_id, "chapters")
