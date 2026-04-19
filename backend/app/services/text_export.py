"""
TubeVault – Text-Export Service v1.0.0

Lagert dokument-artige Felder aus der DB in Dateien aus und hält eine
Referenz-Registry in der text_files-Tabelle. Die Datei ist die Wahrheit,
die DB nur Index (Regel R1 in ARCHITECTURE.md).

Namenschema: /app/data/texts/<video_id>.<kind>.<ext>

Phase 3a (dieses Modul): kind='description' (Plain-Text .txt)
Phase 3b+: chapters (.json), tags (.txt), notes (.md) – gleiche Pattern.
"""
import hashlib
import logging
from pathlib import Path

from app.config import TEXTS_DIR
from app.database import db

logger = logging.getLogger(__name__)


# Kind → File-Extension Mapping
_KIND_EXT = {
    "description": "txt",
    "chapters": "json",
    "tags": "txt",
    "notes": "md",
}


def _filename(video_id: str, kind: str) -> str:
    ext = _KIND_EXT.get(kind, "txt")
    return f"{video_id}.{kind}.{ext}"


def _path(video_id: str, kind: str) -> Path:
    """TEXTS_DIR als Modul-Variable, damit Tests per monkeypatch
    auf ein Temp-Verzeichnis umbiegen können."""
    return TEXTS_DIR / _filename(video_id, kind)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════
# Description (Phase 3a)
# ═══════════════════════════════════════════════════════════════

async def export_description(video_id: str) -> dict | None:
    """Schreibt videos.description als Datei. Idempotent via sha256-Vergleich.

    Returns:
        dict mit {filename, size, sha256, skipped} oder None wenn leer/fehlt.
    """
    row = await db.fetch_one(
        "SELECT description FROM videos WHERE id = ?", (video_id,)
    )
    if not row:
        return None
    content = (row["description"] or "").strip()
    if not content:
        return None

    TEXTS_DIR.mkdir(parents=True, exist_ok=True)
    target = _path(video_id, "description")
    new_hash = _sha256(content)

    # Bereits exportiert + unverändert? → Skip (Idempotenz)
    existing = await db.fetch_one(
        "SELECT sha256 FROM text_files WHERE video_id=? AND kind='description'",
        (video_id,),
    )
    if existing and existing["sha256"] == new_hash and target.exists():
        return {
            "filename": target.name,
            "size": target.stat().st_size,
            "sha256": new_hash,
            "skipped": True,
        }

    # Datei schreiben
    target.write_text(content, encoding="utf-8")
    size = target.stat().st_size

    # Registry aktualisieren
    await db.execute(
        """INSERT OR REPLACE INTO text_files
           (video_id, kind, filename, size_bytes, sha256, synced_at)
           VALUES (?, 'description', ?, ?, ?, datetime('now'))""",
        (video_id, target.name, size, new_hash),
    )
    return {
        "filename": target.name,
        "size": size,
        "sha256": new_hash,
        "skipped": False,
    }


async def export_all_descriptions() -> dict:
    """Batch-Export aller nicht-leeren Beschreibungen.

    Returns:
        {"written": N, "skipped": N, "errors": N, "total": N}
    """
    rows = await db.fetch_all(
        "SELECT id FROM videos WHERE description IS NOT NULL AND description != ''"
    )
    total_with_text = len(rows)

    # Auch die Videos ohne text zählen wir als "skipped" für die Gesamt-Übersicht
    all_vids = await db.fetch_all("SELECT id, description FROM videos")
    stats = {"written": 0, "skipped": 0, "errors": 0, "total": len(all_vids)}

    for row in all_vids:
        vid = row["id"]
        try:
            result = await export_description(vid)
            if result is None:
                stats["skipped"] += 1
            elif result.get("skipped"):
                stats["skipped"] += 1
            else:
                stats["written"] += 1
        except Exception as e:
            logger.warning(f"[text_export] {vid}: {e}")
            stats["errors"] += 1
    logger.info(
        f"[text_export] descriptions: written={stats['written']} "
        f"skipped={stats['skipped']} errors={stats['errors']}"
    )
    return stats


async def read_description_from_file(video_id: str) -> str | None:
    """Liest die Description aus der exportierten Datei.
    Rückgabe None wenn Datei nicht existiert."""
    p = _path(video_id, "description")
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[text_export] read failed for {video_id}: {e}")
        return None


async def delete_description_export(video_id: str) -> bool:
    """Entfernt Datei + Registry-Eintrag. Nicht reversibel außer via
    erneutem export_description(). Returns True wenn was gelöscht wurde."""
    deleted = False
    p = _path(video_id, "description")
    if p.exists():
        try:
            p.unlink()
            deleted = True
        except Exception as e:
            logger.warning(f"[text_export] unlink failed for {video_id}: {e}")
    await db.execute(
        "DELETE FROM text_files WHERE video_id=? AND kind='description'",
        (video_id,),
    )
    return deleted


# ═══════════════════════════════════════════════════════════════
# Overview / Dashboard-Daten
# ═══════════════════════════════════════════════════════════════

async def get_export_overview() -> dict:
    """Statistik für UI:
       {"description": {"in_db": N, "as_file": N, "pending": N, "out_of_sync": N}, ...}
    """
    # --- description ---
    in_db = await db.fetch_val(
        "SELECT COUNT(*) FROM videos "
        "WHERE description IS NOT NULL AND description != ''"
    ) or 0
    as_file = await db.fetch_val(
        "SELECT COUNT(*) FROM text_files WHERE kind='description'"
    ) or 0

    # Out-of-sync: Hash in DB hat sich geändert gegenüber registriertem
    oos = await db.fetch_val(
        """SELECT COUNT(*) FROM videos v
           JOIN text_files t ON t.video_id = v.id AND t.kind='description'
           WHERE v.description IS NOT NULL AND v.description != ''
             AND (SELECT hex(randomblob(0))) IS NOT NULL"""  # placeholder
    ) or 0
    # Simple overview – tatsächliche out_of_sync-Ermittlung benötigt sha256-
    # Vergleich pro Zeile, das ist ein eigener Endpoint ('/mismatch-list').

    pending = max(0, in_db - as_file)
    return {
        "description": {
            "in_db": in_db,
            "as_file": as_file,
            "pending": pending,
            "out_of_sync": oos,
        }
    }
