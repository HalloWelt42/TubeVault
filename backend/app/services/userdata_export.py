"""
TubeVault – Userdata-Export Service v1.0.0

Täglicher JSONL-Export aller NUTZER-Daten – also allem, was sich NICHT aus
den info.json-Sidecars neben den Videos rekonstruieren lässt:
favorites, watch_history, categories (+ Zuordnungen), playlists (+ Inhalte),
subscriptions, blocked_channels, ignored_videos sowie die Nutzerfelder aus
videos (rating, play_count, last_position, notes, suggest_override).

Ablage:  EXPORTS/userdata/userdata_YYYYMMDD_HHMMSS/<tabelle>.jsonl
         + manifest.json (Zeilenzahlen, Zeitpunkt, Schema-Version)
Rotation: die letzten KEEP Exporte bleiben, ältere werden gelöscht.

Zusammen mit den Sidecars (meta_sidecar) und TEXTS_DIR ergibt das den
kompletten Offline-Wiederaufbau: rebuild_service liest beides wieder ein.
"""
import asyncio
import json
import logging
import shutil
from datetime import datetime

from app.database import db
from app.services.storage import storage

logger = logging.getLogger(__name__)

KEEP_EXPORTS = 14

# Ganze Tabellen, die 1:1 gesichert werden
TABLES = [
    "favorites", "watch_history", "categories", "video_categories",
    "playlists", "playlist_videos", "subscriptions",
    "blocked_channels", "ignored_videos",
]

# Nutzerfelder aus videos (nur Zeilen, in denen tatsächlich etwas steht).
# rating hat Spalten-Default 0 (= unbewertet), daher > 0 statt IS NOT NULL.
VIDEO_USERDATA_SQL = """
    SELECT id, rating, play_count, last_position, last_played,
           notes, suggest_override
    FROM videos
    WHERE rating > 0 OR play_count > 0 OR last_position > 0
       OR (notes IS NOT NULL AND notes != '') OR suggest_override IS NOT NULL
"""


def userdata_root():
    return storage.exports_root / "userdata"


def list_exports() -> list[dict]:
    """Vorhandene Export-Ordner, neueste zuerst (sync, billig)."""
    root = userdata_root()
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir() or not d.name.startswith("userdata_"):
            continue
        manifest = {}
        mf = d / "manifest.json"
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        out.append({"folder": d.name, "counts": manifest.get("counts", {}),
                    "created_at": manifest.get("created_at")})
    return out


async def export_userdata() -> dict:
    """Alle Nutzerdaten als JSONL exportieren. Gibt das Manifest zurück."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = userdata_root() / f"userdata_{stamp}"

    # Erst alles aus der DB lesen (async), dann Dateien im Thread schreiben
    dumps: dict[str, list[dict]] = {}
    for table in TABLES:
        rows = await db.fetch_all(f"SELECT * FROM {table}")
        dumps[table] = [dict(r) for r in rows]
    rows = await db.fetch_all(VIDEO_USERDATA_SQL)
    dumps["video_userdata"] = [dict(r) for r in rows]

    counts = {name: len(rows) for name, rows in dumps.items()}
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": await db.fetch_val("SELECT MAX(version) FROM schema_version"),
        "counts": counts,
    }

    def _write():
        target.mkdir(parents=True, exist_ok=True)
        for name, rows_ in dumps.items():
            with (target / f"{name}.jsonl").open("w", encoding="utf-8") as f:
                for r in rows_:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _rotate()

    def _rotate(keep: int = KEEP_EXPORTS):
        dirs = sorted([d for d in userdata_root().iterdir()
                       if d.is_dir() and d.name.startswith("userdata_")])
        for old in dirs[:-keep] if len(dirs) > keep else []:
            shutil.rmtree(old, ignore_errors=True)

    await asyncio.to_thread(_write)
    logger.info(f"[userdata] Export {target.name}: "
                + ", ".join(f"{k}={v}" for k, v in counts.items() if v))
    return {"folder": target.name, **manifest}
