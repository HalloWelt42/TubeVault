"""
TubeVault – Admin Router v1.0.0

Admin-Bereich (kein Login — später). Sammelt Routes für Daten-Management,
Sync-Jobs, System-Inspektion die der User von seiner UI aus steuert.

Aktuell:
- /api/admin/text-export/overview                   → Statistik pro Kind
- /api/admin/text-export/description/sync-all       → Batch-Export
- /api/admin/text-export/description/{video_id}     → Einzel-Export
- /api/admin/text-export/description/{video_id}/file → Raw-File lesen
- DELETE /api/admin/text-export/description/{video_id}
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services import text_export, text_backup, usage_audit
from app.services.storage import storage

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/text-export/overview")
async def overview():
    """Übersicht: wie viele in DB vs. exportiert vs. pending. Inkl. Root-Pfad."""
    data = await text_export.get_export_overview()
    data["texts_root"] = str(storage.texts_root)
    return data


@router.get("/storage/roots")
async def storage_roots():
    """Alle Storage-Roots mit Real-Path (für Admin-UI / Debug)."""
    return {
        "texts": str(storage.texts_root),
        "videos": str(storage.videos_root),
        "thumbnails": str(storage.thumbnails_root),
        "subtitles": str(storage.subtitles_root),
        "avatars": str(storage.avatars_root),
        "banners": str(storage.banners_root),
        "audio": str(storage.audio_root),
        "exports": str(storage.exports_root),
    }


@router.post("/text-export/description/sync-all")
async def sync_all_descriptions():
    """Alle Beschreibungen batch-exportieren (ohne Limit – kann Minuten dauern)."""
    return await text_export.export_all_descriptions()


@router.post("/text-export/description/sync-batch")
async def sync_descriptions_batch(limit: int = 100):
    """Nur die nächsten `limit` AUSSTEHENDEN Beschreibungen exportieren.
    Idempotent, kann mehrmals aufgerufen werden bis remaining_pending = 0."""
    limit = max(1, min(limit, 10000))
    return await text_export.export_all_descriptions(limit=limit)


@router.post("/text-export/chapters/sync-all")
async def sync_all_chapters():
    """Alle Kapitel aller Videos batch-exportieren (kann Minuten dauern)."""
    return await text_export.export_all_chapters()


@router.post("/text-export/chapters/sync-batch")
async def sync_chapters_batch(limit: int = 100):
    """Nur die nächsten `limit` AUSSTEHENDEN Chapter-Listen exportieren."""
    limit = max(1, min(limit, 10000))
    return await text_export.export_all_chapters(limit=limit)


@router.post("/text-export/chapters/{video_id}")
async def sync_chapters_one(video_id: str):
    """Einzelnes Video: chapters.json neu schreiben."""
    result = await text_export.export_chapters(video_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail="Keine Chapters für dieses Video in DB"
        )
    return result


@router.get("/text-export/chapters/{video_id}/file")
async def get_chapters_file(video_id: str):
    """Rohinhalt der chapters.json als JSON-Array ausliefern."""
    data = await text_export.read_chapters_from_file(video_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Keine Export-Datei vorhanden")
    return data


@router.delete("/text-export/chapters/{video_id}")
async def delete_chapters_export_endpoint(video_id: str):
    deleted = await text_export.delete_chapters_export(video_id)
    return {"video_id": video_id, "deleted": deleted}


@router.post("/text-export/description/{video_id}")
async def sync_description(video_id: str):
    """Einzelnen Video-Description-Export ausführen."""
    result = await text_export.export_description(video_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Video oder Beschreibung leer/nicht gefunden",
        )
    return result


@router.get("/text-export/description/{video_id}/file", response_class=PlainTextResponse)
async def get_description_file(video_id: str):
    """Liest den Beschreibungstext direkt aus der Datei (Restore-/Verify-Pfad)."""
    content = await text_export.read_description_from_file(video_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Keine Export-Datei vorhanden")
    return content


@router.delete("/text-export/description/{video_id}")
async def delete_description_export(video_id: str):
    """Export-Datei + Registry-Eintrag entfernen (DB-Description bleibt)."""
    deleted = await text_export.delete_description_export(video_id)
    return {"video_id": video_id, "deleted": deleted}


# ═══════════════════════════════════════════════════════════════
# Meta-Redundanz: Sidecars, Nutzerdaten-Export, Offline-Wiederaufbau
# ═══════════════════════════════════════════════════════════════

@router.get("/redundancy/status")
async def redundancy_status():
    """Gesamt-Status für die Wiederaufbau-Seite: Sidecar-Abdeckung,
    vorhandene Userdata-Exporte, laufende Backfill-/Rebuild-Jobs."""
    from app.services import meta_sidecar, userdata_export
    from app.services.rebuild_service import rebuild_state
    sidecars = await meta_sidecar.sidecar_status()
    return {
        "sidecars": sidecars,
        "userdata_exports": userdata_export.list_exports()[:10],
        "rebuild": dict(rebuild_state),
        "videos_root": str(storage.videos_root),
        "userdata_root": str(userdata_export.userdata_root()),
    }


@router.post("/redundancy/sidecars/backfill")
async def start_sidecar_backfill():
    """Backfill starten: info.json für alle ready-Videos (gedrosselt, idempotent)."""
    import asyncio
    from app.services import meta_sidecar
    if meta_sidecar.backfill_state["running"]:
        raise HTTPException(status_code=409, detail="Backfill läuft bereits")
    asyncio.create_task(meta_sidecar.backfill_sidecars())
    return {"started": True}


@router.post("/redundancy/userdata/export")
async def run_userdata_export():
    """Nutzerdaten sofort als JSONL exportieren (zusätzlich zum Tages-Export)."""
    from app.services import userdata_export
    return await userdata_export.export_userdata()


@router.post("/redundancy/userdata/restore")
async def run_userdata_restore(folder: str = None):
    """Userdata-Export zurückspielen (Default: neuester). Überschreibt nichts
    Frischeres – vorhandene Zeilen/Werte gewinnen."""
    from app.services import rebuild_service
    res = await rebuild_service.restore_userdata(folder)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res


@router.post("/redundancy/rebuild")
async def start_rebuild(dry_run: bool = False):
    """Offline-Rebuild starten: fehlende DB-Einträge aus Sidecars anlegen.
    dry_run=True zählt nur, schreibt nichts."""
    import asyncio
    from app.services import rebuild_service
    if rebuild_service.rebuild_state["running"]:
        raise HTTPException(status_code=409, detail="Rebuild läuft bereits")
    asyncio.create_task(rebuild_service.rebuild_from_sidecars(dry_run=dry_run))
    return {"started": True, "dry_run": dry_run}


# ═══════════════════════════════════════════════════════════════
# Safety: Backup + Audit
# ═══════════════════════════════════════════════════════════════

@router.post("/text-export/backup/descriptions")
async def backup_descriptions():
    """Dumpt alle videos.description als Notfall-Backup (jsonl + sql, gzipped).
    Sollte VOR jedem DB-Leerungs-Versuch laufen.
    Tastet die DB nicht an, reines Lesen."""
    return await text_backup.backup_description_column()


@router.get("/text-export/backup/list")
async def list_backups():
    """Alle vorhandenen Notfall-Backups."""
    return await text_backup.list_backups()


@router.post("/text-export/description/sync-many")
async def sync_descriptions_many(video_ids: list[str]):
    """Bulk-Export für explizit gewählte Video-IDs (max 500 pro Call)."""
    if not video_ids or len(video_ids) > 500:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="1..500 video_ids erwartet")
    stats = {"written": 0, "skipped": 0, "errors": 0}
    for vid in video_ids:
        try:
            r = await text_export.export_description(vid)
            if r is None or r.get("skipped"):
                stats["skipped"] += 1
            else:
                stats["written"] += 1
        except Exception:
            stats["errors"] += 1
    return stats


@router.delete("/text-export/description/bulk")
async def delete_descriptions_bulk(video_ids: list[str]):
    """Bulk-Delete von Export-Dateien (max 500)."""
    if not video_ids or len(video_ids) > 500:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="1..500 video_ids erwartet")
    deleted = 0
    for vid in video_ids:
        if await text_export.delete_description_export(vid):
            deleted += 1
    return {"deleted": deleted, "requested": len(video_ids)}


@router.get("/text-export/description/list")
async def list_descriptions(
    status: str = "all",      # 'exported' | 'pending' | 'all'
    page: int = 1,
    per_page: int = 50,
    search: str = "",
    sort: str = "created_at",  # 'created_at' | 'title' | 'db_length' | 'exported_at' | 'id'
    order: str = "desc",
    channel_id: str = "",
):
    """Tabellarische Liste der Videos mit Description + Export-Status.
    Paginiert, filterbar."""
    from app.database import db as _db
    page = max(1, page)
    per_page = max(10, min(per_page, 500))
    offset = (page - 1) * per_page

    where = ["v.description IS NOT NULL", "v.description != ''"]
    params: list = []
    if status == "exported":
        where.append("t.video_id IS NOT NULL")
    elif status == "pending":
        where.append("t.video_id IS NULL")
    if search:
        where.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if channel_id:
        where.append("v.channel_id = ?")
        params.append(channel_id)

    # Sort-Whitelist (SQL-Injection-Schutz)
    sort_map = {
        "created_at": "v.created_at",
        "title": "v.title COLLATE NOCASE",
        "id": "v.id",
        "db_length": "length(v.description)",
        "exported_at": "t.synced_at",
    }
    sort_col = sort_map.get(sort, "v.created_at")
    order_sql = "DESC" if order.lower() == "desc" else "ASC"

    where_sql = " AND ".join(where)
    total = await _db.fetch_val(
        f"""SELECT COUNT(*) FROM videos v
            LEFT JOIN text_files t ON t.video_id = v.id AND t.kind='description'
            WHERE {where_sql}""",
        tuple(params),
    ) or 0

    rows = await _db.fetch_all(
        f"""SELECT v.id, v.title, v.channel_id, v.channel_name,
                   length(v.description) AS db_length,
                   t.size_bytes AS file_size,
                   t.synced_at AS exported_at,
                   (CASE WHEN t.video_id IS NOT NULL THEN 1 ELSE 0 END) AS exported
            FROM videos v
            LEFT JOIN text_files t ON t.video_id = v.id AND t.kind='description'
            WHERE {where_sql}
            ORDER BY {sort_col} {order_sql}
            LIMIT ? OFFSET ?""",
        tuple(params) + (per_page, offset),
    )
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "status_filter": status,
        "sort": sort,
        "order": order,
        "items": [dict(r) for r in rows],
    }


@router.get("/text-export/audit/description")
async def audit_description():
    """Statischer Code-Scan: wo wird videos.description noch gelesen?
    Solange hier Hits drin sind, NICHT die DB-Spalte leeren."""
    return usage_audit.audit_description()


@router.post("/fts/rebuild")
async def fts_rebuild():
    """FTS5-Volltextindex neu aufbauen – description wird aus dem Resolver
    geholt (File-first), damit die Suche auch nach dem Leeren der DB-Spalte
    weiter funktioniert."""
    from app.database import db as _db
    return await _db.fts_rebuild_from_resolver()


@router.post("/text-export/purge-db-descriptions")
async def purge_description_column(confirm: str = ""):
    """Setzt videos.description = NULL für alle Zeilen. Macht die DB zum Index,
    Files sind ab jetzt die Wahrheit. Wirkt sich nur auf Daten aus, von denen
    ein Export existiert – Sicherheitsnetz gegen Datenverlust.

    Aufruf braucht ?confirm=YES, damit der Endpoint nicht versehentlich
    getriggert wird. Ein Backup (text-export/backup/descriptions) davor ist
    dringend empfohlen."""
    if confirm != "YES":
        raise HTTPException(
            status_code=400,
            detail="Purge erfordert ?confirm=YES. Backup vorher ausführen.",
        )
    from app.database import db as _db
    # Nur Zeilen leeren, für die ein Export existiert – alles andere bleibt
    # als DB-Rest erhalten.
    result = await _db.fetch_val(
        """SELECT COUNT(*) FROM videos v
           WHERE v.description IS NOT NULL AND v.description != ''
             AND EXISTS (SELECT 1 FROM text_files t
                         WHERE t.video_id = v.id AND t.kind = 'description')"""
    ) or 0
    await _db.execute(
        """UPDATE videos
           SET description = NULL
           WHERE description IS NOT NULL AND description != ''
             AND id IN (SELECT video_id FROM text_files WHERE kind = 'description')"""
    )
    left = await _db.fetch_val(
        "SELECT COUNT(*) FROM videos WHERE description IS NOT NULL AND description != ''"
    ) or 0
    return {
        "purged": result,
        "remaining_in_db": left,
        "note": "DB-Spalten geleert, nur wo eine Datei existiert",
    }
