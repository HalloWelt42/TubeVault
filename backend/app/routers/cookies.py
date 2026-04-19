"""
TubeVault Backend – Cookies Router v1.0.0
Upload/Status/Löschen von cookies.txt für yt-dlp-Login-Session.
© HalloWelt42 – Private Nutzung
"""

import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/cookies", tags=["Cookies"])

COOKIES_PATH = Path("/app/config/cookies.txt")


def _status() -> dict:
    """Informativer Status für UI."""
    if not COOKIES_PATH.exists():
        return {"present": False, "size": 0, "mtime": None}
    try:
        st = COOKIES_PATH.stat()
        # Zeilen zählen (ohne Header/Leerzeilen)
        line_count = 0
        with COOKIES_PATH.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    line_count += 1
        return {
            "present": True,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "cookie_count": line_count,
        }
    except Exception as e:
        return {"present": True, "size": 0, "error": str(e)[:120]}


@router.get("")
async def get_status():
    """Status der cookies.txt zurückgeben."""
    return _status()


@router.post("")
async def upload(file: UploadFile = File(...)):
    """cookies.txt hochladen. Ersetzt vorhandene Datei.
    Erwartet Netscape-Format (Browser-Export via 'Get cookies.txt LOCALLY' o.ä.)."""
    # Grobe Validierung: Datei nicht größer als 5 MB, erste Zeile enthält
    # typischen Netscape-Header oder wenigstens domain.com Tab
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Datei")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Datei > 5 MB")
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="Nicht lesbar als UTF-8")
    # Einfacher Format-Check
    if "youtube" not in text.lower() and "google" not in text.lower():
        raise HTTPException(status_code=400,
                            detail="Datei scheint keine YouTube/Google-Cookies zu enthalten")
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COOKIES_PATH.open("w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(COOKIES_PATH, 0o600)
    return _status()


@router.delete("")
async def delete():
    """cookies.txt entfernen (Cookies-Login deaktivieren)."""
    if COOKIES_PATH.exists():
        COOKIES_PATH.unlink()
    return {"present": False}
