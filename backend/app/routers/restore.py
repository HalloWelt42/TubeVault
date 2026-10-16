"""
TubeVault - Wiederherstellen (Einstellungen > System, Entwurf mockups/werkzeuge.html)

Notfallwerkzeuge neben der Sicherung: die Datenbank aus den Begleitdateien
neu aufbauen (mit Probelauf) und Nutzerdaten sichern oder zurückspielen.
Inhalte liegen als Datei neben den Videos (content_files); was dort noch
fehlt, zieht der Hintergrund selbst nach.
"""
import asyncio

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/restore", tags=["Wiederherstellen"])


@router.get("/status")
async def restore_status():
    """Stand für die Karte "Wiederherstellen": Nutzerdaten-Sicherungen,
    laufender Wiederaufbau, noch fehlende Inhaltsdateien."""
    from app.services import content_files, userdata_export
    from app.services.rebuild_service import rebuild_state
    return {
        "userdata_exports": userdata_export.list_exports()[:10],
        "rebuild": dict(rebuild_state),
        "content_files_missing": await content_files.remaining(),
    }


@router.post("/userdata/export")
async def export_userdata_now():
    """Nutzerdaten sofort als Datei sichern (zusätzlich zur täglichen Sicherung)."""
    from app.services import userdata_export
    return await userdata_export.export_userdata()


@router.post("/userdata/restore")
async def restore_userdata(folder: str = None):
    """Eine Nutzerdaten-Sicherung zurückspielen (Standard: die neueste).
    Überschreibt nichts Frischeres - vorhandene Zeilen und Werte gewinnen."""
    from app.services import rebuild_service
    result = await rebuild_service.restore_userdata(folder)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/rebuild")
async def start_rebuild(dry_run: bool = False):
    """Fehlende Datenbankeinträge aus den Begleitdateien anlegen; dry_run zählt nur."""
    from app.services import rebuild_service
    if rebuild_service.rebuild_state["running"]:
        raise HTTPException(status_code=409, detail="Der Wiederaufbau läuft bereits")
    asyncio.create_task(rebuild_service.rebuild_from_sidecars(dry_run=dry_run))
    return {"started": True, "dry_run": dry_run}
