"""
TubeVault -  Backup Router v1.5.79
DB-Backup erstellen, herunterladen, wiederherstellen.
© HalloWelt42 -  Private Nutzung
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.config import DATA_DIR, DB_DIR, EXPORTS_DIR, VERSION
from app.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["Backup"])

BACKUP_DIR = EXPORTS_DIR / "backups"


@router.post("/create")
async def create_backup(frontend_version: str = None):
    """SQLite-Datenbank sicher als Backup exportieren (VACUUM INTO)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    be_ver = VERSION.replace(".", "-")
    fe_ver = (frontend_version or VERSION).replace(".", "-")
    filename = f"tubevault_backup_{ts}_be{be_ver}_fe{fe_ver}.db"
    dest = BACKUP_DIR / filename

    try:
        # VACUUM INTO erstellt eine konsistente Kopie ohne WAL-Reste
        await db.execute(f'VACUUM INTO "{str(dest)}"')
        size = dest.stat().st_size
        logger.info(f"[BACKUP] Erstellt: {filename} ({size} bytes)")

        return {
            "status": "ok",
            "filename": filename,
            "size": size,
            "created_at": ts,
        }
    except Exception as e:
        # Fallback: Datei-Kopie
        logger.warning(f"[BACKUP] VACUUM INTO fehlgeschlagen: {e}, nutze Datei-Kopie")
        src = DB_DIR / "tubevault.db"
        if not src.exists():
            raise HTTPException(status_code=500, detail="Datenbank nicht gefunden")
        try:
            # WAL checkpoint bevor kopiert wird
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        shutil.copy2(str(src), str(dest))
        size = dest.stat().st_size
        return {
            "status": "ok",
            "filename": filename,
            "size": size,
            "created_at": ts,
            "method": "file_copy",
        }


@router.get("/list")
async def list_backups():
    """Alle vorhandenen Backups auflisten."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for f in sorted(BACKUP_DIR.glob("tubevault_backup_*.db"), reverse=True):
        st = f.stat()
        backups.append({
            "filename": f.name,
            "size": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
        })
    return {"backups": backups}


@router.get("/download/{filename}")
async def download_backup(filename: str):
    """Backup-Datei herunterladen."""
    # Sicherheitscheck: kein Path-Traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    path = BACKUP_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup nicht gefunden")

    return FileResponse(
        str(path),
        media_type="application/x-sqlite3",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/delete/{filename}")
async def delete_backup(filename: str):
    """Backup-Datei löschen."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    path = BACKUP_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup nicht gefunden")

    path.unlink()
    logger.info(f"[BACKUP] Gelöscht: {filename}")
    return {"status": "ok", "deleted": filename}


@router.post("/restore/{filename}")
async def restore_backup(filename: str):
    """Backup wiederherstellen. Ersetzt die aktive DB.
    ACHTUNG: Daten gehen verloren!"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup nicht gefunden")

    db_path = DB_DIR / "tubevault.db"

    # Sicherheits-Backup der aktuellen DB
    safety_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_name = f"tubevault_pre_restore_{safety_ts}.db"
    safety_path = BACKUP_DIR / safety_name

    try:
        # 1. Aktuellen Zustand sichern
        await db.execute(f'VACUUM INTO "{str(safety_path)}"')
        logger.info(f"[RESTORE] Sicherheits-Backup: {safety_name}")
    except Exception:
        # Fallback
        try:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        shutil.copy2(str(db_path), str(safety_path))

    try:
        # 2. Verbindung schließen
        await db.disconnect()

        # 3. WAL-Dateien entfernen
        wal = db_path.with_suffix(".db-wal")
        shm = db_path.with_suffix(".db-shm")
        if wal.exists():
            wal.unlink()
        if shm.exists():
            shm.unlink()

        # 4. Backup kopieren
        shutil.copy2(str(backup_path), str(db_path))

        # 5. Verbindung neu öffnen
        await db.connect()
        await db._init_schema()

        logger.info(f"[RESTORE] Wiederhergestellt aus: {filename}")
        return {
            "status": "ok",
            "restored_from": filename,
            "safety_backup": safety_name,
        }
    except Exception as e:
        logger.error(f"[RESTORE] Fehler: {e}")
        # Versuch: Safety-Backup zurückspielen
        try:
            shutil.copy2(str(safety_path), str(db_path))
            await db.connect()
            await db._init_schema()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Restore fehlgeschlagen: {e}")


@router.post("/restore-upload")
async def restore_from_upload(file: UploadFile = File(...)):
    """Backup aus Upload wiederherstellen."""
    if not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Nur .db Dateien erlaubt")

    # Temporär speichern
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_name = f"tubevault_uploaded_{ts}.db"
    upload_path = BACKUP_DIR / upload_name

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Datei zu klein -  keine gültige DB")

    # SQLite Magic Number Check
    if content[:16] != b"SQLite format 3\x00":
        raise HTTPException(status_code=400, detail="Keine gültige SQLite-Datenbank")

    upload_path.write_bytes(content)
    logger.info(f"[RESTORE] Upload gespeichert: {upload_name} ({len(content)} bytes)")

    # Restore via vorhandene Funktion
    return await restore_backup(upload_name)


@router.get("/stats")
async def backup_stats():
    """Statistiken über DB und Backups."""
    db_path = DB_DIR / "tubevault.db"
    db_size = db_path.stat().st_size if db_path.exists() else 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_files = list(BACKUP_DIR.glob("tubevault_*.db"))
    backup_size = sum(f.stat().st_size for f in backup_files)

    # Tabellen-Größen
    tables = {}
    for tbl in ["videos", "chapters", "rss_entries", "subscriptions",
                 "jobs", "categories", "settings", "streams",
                 "video_links", "playlists", "video_archives"]:
        try:
            count = await db.fetch_val(f"SELECT COUNT(*) FROM {tbl}")
            tables[tbl] = count or 0
        except Exception:
            tables[tbl] = -1

    return {
        "db_size": db_size,
        "backup_count": len(backup_files),
        "backup_total_size": backup_size,
        "tables": tables,
    }
