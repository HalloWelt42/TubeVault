"""
TubeVault – Counts Service v1.0.0

EINE Quelle der Wahrheit für alle Zählungen (Badges, Dashboard-Stats,
Queue-Tabs, Disk). Jede Definition steht genau einmal hier, dokumentiert;
die Endpoints (system/badges, system/stats, jobs/stats, downloads/queue)
komponieren daraus statt eigene, divergierende SQL zu führen.

Leitregel: **Ein Badge zählt exakt das, was seine Zielseite anzeigt.**
- videos      == Library-Seite  (ready & non-archived, jede source)
- archives    == Archiv-Seite   (ready & archived)
- own_videos  == OwnVideos-Seite (source local/imported, ready, echte Datei)
  → Fix ggü. früher: file_size>0 wie die Seite; KEIN Archiv-Filter, weil die
    Seite archivierte eigene Videos ebenfalls listet.
"""
import logging
import os

from app.database import db
from app.config import VIDEOS_DIR, DB_DIR

logger = logging.getLogger(__name__)


class CountsService:
    # ─── Bibliothek / Videos ──────────────────────────────────────
    async def library_videos(self) -> int:
        """Ready & nicht archiviert (jede source) – wie die Library-Seite."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE status='ready' AND COALESCE(is_archived,0)=0"
        ) or 0

    async def archived_videos(self) -> int:
        """Ready & archiviert – wie die Archiv-Seite."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE status='ready' AND COALESCE(is_archived,0)=1"
        ) or 0

    async def own_videos(self) -> int:
        """Eigene/importierte mit echter Datei – wie die OwnVideos-Seite
        (import_service.get_own_videos: source, ready, file_path, file_size>0)."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE source IN ('local','imported') "
            "AND status='ready' AND file_path IS NOT NULL AND file_path != '' "
            "AND file_size > 0"
        ) or 0

    async def library_size_bytes(self) -> int:
        return await db.fetch_val(
            "SELECT COALESCE(SUM(file_size),0) FROM videos "
            "WHERE status='ready' AND COALESCE(is_archived,0)=0"
        ) or 0

    async def library_duration_seconds(self) -> int:
        return await db.fetch_val(
            "SELECT COALESCE(SUM(duration),0) FROM videos "
            "WHERE status='ready' AND COALESCE(is_archived,0)=0"
        ) or 0

    # ─── Feed / Abos ──────────────────────────────────────────────
    async def feed_new(self) -> int:
        """Neue RSS-Einträge in aktiven Feeds – wie das Feed-Badge/-Tab."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE status='new' "
            "AND COALESCE(feed_status,'active')='active'"
        ) or 0

    async def subscriptions_enabled(self) -> int:
        return await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE enabled=1"
        ) or 0

    async def subscriptions_total(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0

    async def subscriptions_error(self) -> int:
        return await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE error_count > 0"
        ) or 0

    # ─── Sammlungen ───────────────────────────────────────────────
    async def favorites(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM favorites") or 0

    async def playlists_global(self) -> int:
        """Globale Playlists (Badge) – ohne versteckte/lokale."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM playlists WHERE COALESCE(visibility,'global')='global'"
        ) or 0

    async def playlists_total(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM playlists") or 0

    async def categories(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM categories") or 0

    async def streams(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM streams") or 0

    # ─── Verlauf (zwei bewusst getrennte Konzepte) ────────────────
    async def history_played(self) -> int:
        """Videos, die mind. 1× abgespielt wurden (Badge zeigt „Verlauf")."""
        return await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE play_count > 0"
        ) or 0

    async def history_entries(self) -> int:
        """Distinkte Videos in der watch_history (Stats – kann abweichen,
        z.B. wenn play_count zurückgesetzt wurde). Dokumentierte Divergenz."""
        return await db.fetch_val(
            "SELECT COUNT(DISTINCT video_id) FROM watch_history"
        ) or 0

    # ─── Disk ─────────────────────────────────────────────────────
    def disk_mounts(self) -> dict:
        """Immer beide Mounts mit Label + Nutzung; same_device via st_dev
        (löst die alte >1GB-Heuristik ab, die gleich große Platten verbarg)."""
        from app.utils.file_utils import get_disk_usage
        media = get_disk_usage(str(VIDEOS_DIR)); media["label"] = "Medien"
        meta = get_disk_usage(str(DB_DIR)); meta["label"] = "System"
        same = False
        try:
            same = os.stat(VIDEOS_DIR).st_dev == os.stat(DB_DIR).st_dev
        except OSError:
            pass
        return {"media": media, "meta": meta, "same_device": same}


# Singleton
counts_service = CountsService()
