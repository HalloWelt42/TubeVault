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

from app.services import text_export

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/text-export/overview")
async def overview():
    """Übersicht: wie viele in DB vs. exportiert vs. pending."""
    return await text_export.get_export_overview()


@router.post("/text-export/description/sync-all")
async def sync_all_descriptions():
    """Alle Beschreibungen batch-exportieren."""
    return await text_export.export_all_descriptions()


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
