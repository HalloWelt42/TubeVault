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
    target.parent.mkdir(parents=True, exist_ok=True)
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

    target.write_text(content, encoding="utf-8")
    size = target.stat().st_size
    await db.execute(
        """INSERT OR REPLACE INTO text_files
           (video_id, kind, filename, size_bytes, sha256, synced_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (video_id, kind, rel_name, size, new_hash),
    )
    return {
        "filename": rel_name,
        "size": size,
        "sha256": new_hash,
        "skipped": False,
    }


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
    # Ordner aufräumen wenn leer (lässt andere Kinds-Files unberührt)
    try:
        d = _resolve_video_dir(video_id)
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
    except Exception:
        pass
    return deleted


async def _read_text_file(video_id: str, kind: str) -> str | None:
    p = _resolve_text_file(video_id, kind)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[text_export] read failed for {video_id} {kind}: {e}")
        return None


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


async def export_all_descriptions(limit: int | None = None) -> dict:
    """Batch-Export der Beschreibungen."""
    if limit is not None and limit > 0:
        rows = await db.fetch_all(
            """SELECT v.id FROM videos v
               LEFT JOIN text_files t ON t.video_id = v.id AND t.kind='description'
               WHERE v.description IS NOT NULL AND v.description != ''
                 AND t.video_id IS NULL
               ORDER BY v.id
               LIMIT ?""",
            (limit,)
        )
        iterate_ids = [r["id"] for r in rows]
    else:
        all_vids = await db.fetch_all("SELECT id FROM videos")
        iterate_ids = [r["id"] for r in all_vids]

    stats = {"written": 0, "skipped": 0, "errors": 0, "total": len(iterate_ids)}
    for vid in iterate_ids:
        try:
            result = await export_description(vid)
            if result is None or result.get("skipped"):
                stats["skipped"] += 1
            else:
                stats["written"] += 1
        except Exception as e:
            logger.warning(f"[text_export] {vid}: {e}")
            stats["errors"] += 1

    remaining = await db.fetch_val(
        """SELECT COUNT(*) FROM videos v
           LEFT JOIN text_files t ON t.video_id = v.id AND t.kind='description'
           WHERE v.description IS NOT NULL AND v.description != ''
             AND t.video_id IS NULL"""
    ) or 0
    stats["remaining_pending"] = remaining
    stats["limit"] = limit
    return stats


async def read_description_from_file(video_id: str) -> str | None:
    return await _read_text_file(video_id, "description")


async def delete_description_export(video_id: str) -> bool:
    return await _delete_text_file(video_id, "description")


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


async def export_all_chapters(limit: int | None = None) -> dict:
    """Batch-Export aller Chapter-Listen."""
    if limit is not None and limit > 0:
        rows = await db.fetch_all(
            """SELECT DISTINCT c.video_id FROM chapters c
               LEFT JOIN text_files t ON t.video_id = c.video_id AND t.kind='chapters'
               WHERE t.video_id IS NULL
               ORDER BY c.video_id
               LIMIT ?""",
            (limit,),
        )
        iterate_ids = [r["video_id"] for r in rows]
    else:
        rows = await db.fetch_all("SELECT DISTINCT video_id FROM chapters")
        iterate_ids = [r["video_id"] for r in rows]

    stats = {"written": 0, "skipped": 0, "errors": 0, "total": len(iterate_ids)}
    for vid in iterate_ids:
        try:
            result = await export_chapters(vid)
            if result is None or result.get("skipped"):
                stats["skipped"] += 1
            else:
                stats["written"] += 1
        except Exception as e:
            logger.warning(f"[text_export] chapters {vid}: {e}")
            stats["errors"] += 1

    remaining = await db.fetch_val(
        """SELECT COUNT(DISTINCT c.video_id) FROM chapters c
           LEFT JOIN text_files t ON t.video_id = c.video_id AND t.kind='chapters'
           WHERE t.video_id IS NULL"""
    ) or 0
    stats["remaining_pending"] = remaining
    stats["limit"] = limit
    return stats


async def read_chapters_from_file(video_id: str) -> list | None:
    """Liest chapters.json als Array zurück. None wenn Datei fehlt/ungültig."""
    raw = await _read_text_file(video_id, "chapters")
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


async def delete_chapters_export(video_id: str) -> bool:
    return await _delete_text_file(video_id, "chapters")


# ═══════════════════════════════════════════════════════════════
# Overview / Dashboard-Daten
# ═══════════════════════════════════════════════════════════════

async def get_export_overview() -> dict:
    """Statistik für UI. Liefert pro Kind: in_db, as_file, pending."""
    # description
    desc_in_db = await db.fetch_val(
        "SELECT COUNT(*) FROM videos "
        "WHERE description IS NOT NULL AND description != ''"
    ) or 0
    desc_as_file = await db.fetch_val(
        "SELECT COUNT(*) FROM text_files WHERE kind='description'"
    ) or 0

    # chapters: Videos, die mind. 1 Chapter-Zeile haben
    chap_in_db = await db.fetch_val(
        "SELECT COUNT(DISTINCT video_id) FROM chapters"
    ) or 0
    chap_as_file = await db.fetch_val(
        "SELECT COUNT(*) FROM text_files WHERE kind='chapters'"
    ) or 0

    return {
        "description": {
            "in_db": desc_in_db,
            "as_file": desc_as_file,
            "pending": max(0, desc_in_db - desc_as_file),
            "out_of_sync": 0,
        },
        "chapters": {
            "in_db": chap_in_db,
            "as_file": chap_as_file,
            "pending": max(0, chap_in_db - chap_as_file),
            "out_of_sync": 0,
        },
    }
