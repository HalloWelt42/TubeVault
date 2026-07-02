"""
TubeVault – Meta-Sidecar Service v1.0.0

Bewusste Meta-Redundanz: neben jedem Video liegt eine info.json mit den
wichtigsten Metadaten aus der DB (VIDEOS_DIR/<id>/info.json). Geht die DB
verloren, lässt sich der Index aus den Dateien wiederherstellen – ohne
Internet. Die DB bleibt Index (Regel R1), die Datei repliziert den Eintrag.

Idempotent: Der Inhalt ist eine pure Funktion der DB-Zeile (bewusst KEINE
Zeitstempel im Payload) – unveränderte Daten führen zu keinem erneuten
Schreiben (Inhalts-Vergleich). Das Export-Datum ist die Datei-mtime.

write_sidecar() wirft nie – Hook-Aufrufer (Download/Import/Update) bleiben
Einzeiler ohne eigenes Error-Handling.
"""
import asyncio
import json
import logging

from app.database import db
from app.services.storage import storage

logger = logging.getLogger(__name__)

SIDECAR_VERSION = 1
SIDECAR_NAME = "info.json"

# Reihenfolge = Datei-Layout. Nutzerdaten (rating, play_count, notes,
# favorites, history) gehören NICHT hierher – die sichert der
# Userdata-Export. description/chapters liegen bereits in TEXTS_DIR.
_FIELDS = [
    "id", "title", "channel_id", "channel_name",
    "upload_date", "download_date", "duration",
    "view_count", "like_count", "dislike_count",
    "source", "source_url", "video_type",
    "is_music", "music_artist", "music_title", "music_album",
    "is_archived", "file_size",
]


def sidecar_path(video_id: str):
    """VIDEOS_DIR/<id>/info.json – direkt neben video.mp4."""
    return storage.videos_root / video_id / SIDECAR_NAME


def build_payload(row) -> dict:
    """Sidecar-Inhalt aus einer videos-Zeile (Row oder dict). Pure Funktion."""
    d = dict(row)
    payload = {"sidecar_version": SIDECAR_VERSION}
    for f in _FIELDS:
        payload[f] = d.get(f)
    # tags liegen in der DB als JSON-String – im Sidecar als echte Liste
    raw = d.get("tags")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            payload["tags"] = parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            payload["tags"] = [t.strip() for t in raw.split(",") if t.strip()]
    else:
        payload["tags"] = []
    return payload


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


async def write_sidecar(video_id: str) -> dict:
    """info.json für ein Video schreiben. Idempotent, wirft nie.

    Rückgabe: {"written": True} | {"skipped": True, "reason": ...} |
              {"missing": True} | {"error": ...}
    Es wird nur in EXISTIERENDE Video-Ordner geschrieben – für Einträge
    ohne Ordner (RSS-Platzhalter, Ghosts) entstehen keine Leichen-Ordner.
    """
    try:
        row = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not row:
            return {"missing": True}
        content = _canonical(build_payload(row))
        target = sidecar_path(video_id)

        def _write() -> dict:
            if not target.parent.is_dir():
                return {"skipped": True, "reason": "kein Video-Ordner"}
            if target.exists():
                try:
                    if target.read_text(encoding="utf-8") == content:
                        return {"skipped": True, "reason": "unverändert"}
                except OSError:
                    pass
            target.write_text(content, encoding="utf-8")
            return {"written": True}

        # Datei-I/O auf der (USB-)Platte nie auf dem Event-Loop
        return await asyncio.to_thread(_write)
    except Exception as e:
        logger.warning(f"[sidecar] {video_id}: {e}")
        return {"error": str(e)}


def read_sidecar_file(path) -> dict | None:
    """Sidecar-Datei lesen und validieren (sync – für Rebuild-Scans)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "sidecar_version" not in data:
            return None
        if not data.get("id"):
            return None
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return None


async def read_sidecar(video_id: str) -> dict | None:
    path = sidecar_path(video_id)
    return await asyncio.to_thread(read_sidecar_file, path)


# ═══════════════════════════════════════════════════════════════
# Backfill – einmalig alle vorhandenen Videos mit Sidecars versorgen
# ═══════════════════════════════════════════════════════════════

# Fortschritt für Admin-UI (ein Backfill zur Zeit)
backfill_state = {"running": False, "done": 0, "total": 0,
                  "written": 0, "skipped": 0, "errors": 0}


async def backfill_sidecars(throttle_every: int = 50,
                            throttle_sleep: float = 0.1) -> dict:
    """Sidecars für alle ready-Videos schreiben (gedrosselt, idempotent).

    Drosselung: alle `throttle_every` Videos eine kurze Pause, damit die
    USB-Platte und der Event-Loop Luft behalten (23k+ Ordner).
    """
    if backfill_state["running"]:
        return {"error": "Backfill läuft bereits"}
    rows = await db.fetch_all("SELECT id FROM videos WHERE status = 'ready'")
    backfill_state.update(running=True, done=0, total=len(rows),
                          written=0, skipped=0, errors=0)
    logger.info(f"[sidecar] Backfill startet: {len(rows)} Videos")
    try:
        for i, r in enumerate(rows):
            res = await write_sidecar(r["id"])
            backfill_state["done"] = i + 1
            if res.get("written"):
                backfill_state["written"] += 1
            elif res.get("skipped"):
                backfill_state["skipped"] += 1
            else:
                backfill_state["errors"] += 1
            if throttle_every and (i + 1) % throttle_every == 0:
                await asyncio.sleep(throttle_sleep)
    finally:
        backfill_state["running"] = False
    logger.info(
        f"[sidecar] Backfill fertig: {backfill_state['written']} geschrieben, "
        f"{backfill_state['skipped']} unverändert/übersprungen, "
        f"{backfill_state['errors']} Fehler")
    return dict(backfill_state)


async def sidecar_status() -> dict:
    """Bestandsaufnahme für die Admin-UI: wie viele Sidecars existieren?"""
    rows = await db.fetch_all("SELECT id FROM videos WHERE status = 'ready'")
    ids = [r["id"] for r in rows]

    def _count() -> int:
        n = 0
        for vid in ids:
            if (storage.videos_root / vid / SIDECAR_NAME).exists():
                n += 1
        return n

    present = await asyncio.to_thread(_count)
    return {
        "videos_ready": len(ids),
        "sidecars_present": present,
        "sidecars_missing": len(ids) - present,
        "backfill": dict(backfill_state),
    }
