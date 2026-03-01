"""
TubeVault -  Metadata Service v1.3.0
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import json
import logging
from datetime import datetime

from app.database import db
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags

logger = logging.getLogger(__name__)


class MetadataService:
    """Video-Metadaten verwalten und anreichern."""

    async def get_video(self, video_id: str) -> dict | None:
        """Einzelnes Video mit allen Details abrufen."""
        row = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not row:
            return None
        result = self._row_to_dict(row)
        # Kategorie-IDs und -Namen anhängen
        cats = await db.fetch_all(
            """SELECT c.id, c.name, c.color FROM video_categories vc
               JOIN categories c ON vc.category_id = c.id
               WHERE vc.video_id = ?""",
            (video_id,)
        )
        result["category_ids"] = [c["id"] for c in cats]
        result["category"] = cats[0]["name"] if cats else None
        return result

    async def get_videos(
        self,
        page: int = 1,
        per_page: int = 24,
        status: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        search: str | None = None,
        category_id: int | None = None,
        category_ids: str | None = None,
        channel_id: str | None = None,
        channel_ids: str | None = None,
        tag: str | None = None,
        tags: str | None = None,
        video_type: str | None = None,
        video_types: str | None = None,
        is_archived: bool | None = None,
        is_music: bool | None = None,
    ) -> dict:
        """Videos mit Paginierung, Filter und Sortierung abrufen.
        Mehrfachfilter: category_ids, channel_ids, video_types als Komma-getrennte Werte.
        is_archived: True=nur archivierte, False=nur nicht-archivierte, None=alle.
        """
        conditions = []
        params = []

        # Archiv-Filter (Standard: nicht-archiviert)
        if is_archived is True:
            conditions.append("COALESCE(v.is_archived, 0) = 1")
        elif is_archived is False:
            conditions.append("COALESCE(v.is_archived, 0) = 0")

        if status:
            conditions.append("v.status = ?")
            params.append(status)
        else:
            # Standard: nur 'ready' Videos anzeigen (keine Stubs/Bookmarks/Pending)
            conditions.append("v.status = 'ready'")

        if search:
            conditions.append("(v.title LIKE ? OR v.channel_name LIKE ? OR v.description LIKE ? OR v.notes LIKE ?)")
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term, search_term])

        # Kategorie-Filter: Mehrfach (category_ids) hat Vorrang vor Einzel (category_id)
        cat_ids = self._parse_multi_int(category_ids) if category_ids else ([category_id] if category_id else [])
        if cat_ids:
            placeholders = ",".join("?" * len(cat_ids))
            conditions.append(f"v.id IN (SELECT video_id FROM video_categories WHERE category_id IN ({placeholders}))")
            params.extend(cat_ids)

        # Kanal-Filter: Mehrfach (channel_ids) hat Vorrang vor Einzel (channel_id)
        ch_ids = self._parse_multi_str(channel_ids) if channel_ids else ([channel_id] if channel_id else [])
        if ch_ids:
            placeholders = ",".join("?" * len(ch_ids))
            conditions.append(f"v.channel_id IN ({placeholders})")
            params.extend(ch_ids)

        # Video-Typ-Filter: Mehrfach (video_types) hat Vorrang vor Einzel (video_type)
        vtypes = self._parse_multi_str(video_types) if video_types else ([video_type] if video_type else [])
        if vtypes:
            placeholders = ",".join("?" * len(vtypes))
            conditions.append(f"COALESCE(v.video_type, 'video') IN ({placeholders})")
            params.extend(vtypes)

        # Tag-Filter: Mehrfach (tags) hat Vorrang vor Einzel (tag), OR-verknüpft
        tag_list = self._parse_multi_str(tags) if tags else ([tag] if tag else [])
        if tag_list:
            tag_conditions = []
            for t in tag_list:
                tag_conditions.append("v.tags LIKE ?")
                params.append(f'%"{t}"%')
            conditions.append(f"({' OR '.join(tag_conditions)})")

        # Musik-Filter
        if is_music is True:
            conditions.append("v.is_music = 1")
        elif is_music is False:
            conditions.append("COALESCE(v.is_music, 0) = 0")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Erlaubte Sortierfelder
        allowed_sorts = {
            "created_at", "updated_at", "title", "duration",
            "download_date", "rating", "play_count", "file_size",
            "channel_name", "upload_date",
        }
        if sort_by not in allowed_sorts:
            sort_by = "created_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Total Count
        total = await db.fetch_val(f"SELECT COUNT(*) FROM videos v {where}", params)

        # Paginierte Ergebnisse
        offset = (page - 1) * per_page
        rows = await db.fetch_all(
            f"""SELECT v.* FROM videos v {where}
                ORDER BY v.{sort_by} {order}
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        )

        total_pages = max(1, (total + per_page - 1) // per_page)

        return {
            "videos": [self._row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    async def update_video(self, video_id: str, updates: dict) -> dict | None:
        """Video-Metadaten aktualisieren."""
        # Category-IDs separat behandeln (M:N über video_categories)
        category_ids = updates.pop("category_ids", None)
        category_name = updates.pop("category", None)

        if category_ids is not None:
            # Explizite ID-Liste: alte löschen, neue setzen
            await db.execute("DELETE FROM video_categories WHERE video_id = ?", (video_id,))
            for cid in category_ids:
                await db.execute(
                    "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
                    (video_id, cid)
                )
        elif category_name is not None:
            # Legacy: Kategorie per Name
            await db.execute("DELETE FROM video_categories WHERE video_id = ?", (video_id,))
            if category_name:
                cat = await db.fetch_one(
                    "SELECT id FROM categories WHERE name = ?", (category_name,)
                )
                if cat:
                    await db.execute(
                        "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
                        (video_id, cat["id"])
                    )

        # suggest_override: Spezialbehandlung für Reset (leerer String = NULL)
        suggest_override_raw = updates.pop("suggest_override", None)
        reset_suggest = False
        if suggest_override_raw is not None:
            if suggest_override_raw in ("", "reset", "null"):
                reset_suggest = True  # Explizit auf NULL setzen

        allowed = {"title", "description", "channel_name", "notes", "rating", "tags", "video_type"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}

        # suggest_override nach filtered-Erstellung einfügen
        if suggest_override_raw in ("include", "exclude"):
            filtered["suggest_override"] = suggest_override_raw

        # video_type validieren
        if "video_type" in filtered and filtered["video_type"] not in ("video", "short", "live"):
            filtered.pop("video_type")

        if not filtered and not reset_suggest and category_ids is None and category_name is None:
            return await self.get_video(video_id)

        if "tags" in filtered:
            filtered["tags"] = json.dumps(sanitize_tags(filtered["tags"]))

        if reset_suggest:
            await db.execute(
                "UPDATE videos SET suggest_override = NULL, updated_at = ? WHERE id = ?",
                (now_sqlite(), video_id))

        if filtered:
            filtered["updated_at"] = now_sqlite()
            set_clause = ", ".join(f"{k} = ?" for k in filtered)
            values = list(filtered.values()) + [video_id]
            await db.execute(
                f"UPDATE videos SET {set_clause} WHERE id = ?", values
            )

        # video_type auch in rss_entries synchronisieren
        if "video_type" in updates and updates["video_type"] in ("video", "short", "live"):
            await db.execute(
                "UPDATE rss_entries SET video_type = ? WHERE video_id = ?",
                (updates["video_type"], video_id)
            )

        return await self.get_video(video_id)

    async def delete_video(self, video_id: str) -> bool:
        """Video und zugehörige Dateien + DB-Einträge löschen."""
        import shutil
        from app.config import VIDEOS_DIR, THUMBNAILS_DIR, SUBTITLES_DIR, AUDIO_DIR

        video = await self.get_video(video_id)
        if not video:
            return False

        # Dateien löschen
        for base_dir in (VIDEOS_DIR, THUMBNAILS_DIR, SUBTITLES_DIR, AUDIO_DIR):
            vid_dir = base_dir / video_id
            if vid_dir.exists():
                shutil.rmtree(vid_dir)

        # Alle verknüpften DB-Einträge manuell löschen (kein CASCADE auf video_id)
        await db.execute("DELETE FROM video_categories WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM favorites WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM playlist_videos WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM watch_history WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM streams WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM stream_combinations WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
        await db.execute("DELETE FROM jobs WHERE type='download' AND json_extract(metadata, '$.video_id') = ?", (video_id,))
        # rss_entries NICHT löschen → Katalog bleibt erhalten

        # Video selbst löschen
        await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))

        # Playlist video_counts aktualisieren
        await db.execute(
            """UPDATE playlists SET video_count = (
                SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = playlists.id
            )"""
        )

        logger.info(f"Video gelöscht: {video_id} (inkl. Favoriten, Playlists, History)")
        return True

    async def record_play(self, video_id: str, position: int = 0):
        """Wiedergabe aufzeichnen."""
        now = now_sqlite()
        await db.execute(
            "UPDATE videos SET play_count = play_count + 1, last_played = ?, updated_at = ? WHERE id = ?",
            (now, now, video_id)
        )
        await db.execute(
            "INSERT INTO watch_history (video_id, position) VALUES (?, ?)",
            (video_id, position)
        )

    async def save_position(self, video_id: str, position: int):
        """Wiedergabeposition speichern (auf videos + watch_history)."""
        await db.execute(
            "UPDATE videos SET last_position = ? WHERE id = ?",
            (position, video_id)
        )
        await db.execute(
            """INSERT OR REPLACE INTO watch_history (video_id, position, watched_at)
               VALUES (?, ?, datetime('now'))""",
            (video_id, position)
        )

    async def get_last_position(self, video_id: str) -> int:
        """Letzte Wiedergabeposition abrufen."""
        val = await db.fetch_val(
            "SELECT last_position FROM videos WHERE id = ?",
            (video_id,)
        )
        return val or 0

    async def get_watch_history(
        self,
        page: int = 1,
        per_page: int = 24,
        search: str | None = None,
        channel_id: str | None = None,
        channel_ids: str | None = None,
        video_type: str | None = None,
        video_types: str | None = None,
    ) -> dict:
        """Watch-History mit Video-Details und Filtern abrufen."""
        conditions = []
        params = []

        if search:
            conditions.append("(v.title LIKE ? OR v.channel_name LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term])

        # Kanal-Filter
        ch_ids = self._parse_multi_str(channel_ids) if channel_ids else ([channel_id] if channel_id else [])
        if ch_ids:
            placeholders = ",".join("?" * len(ch_ids))
            conditions.append(f"v.channel_id IN ({placeholders})")
            params.extend(ch_ids)

        # Video-Typ-Filter
        vtypes = self._parse_multi_str(video_types) if video_types else ([video_type] if video_type else [])
        if vtypes:
            placeholders = ",".join("?" * len(vtypes))
            conditions.append(f"COALESCE(v.video_type, 'video') IN ({placeholders})")
            params.extend(vtypes)

        extra_where = f"AND {' AND '.join(conditions)}" if conditions else ""

        total = await db.fetch_val(
            f"""SELECT COUNT(DISTINCT wh.video_id)
                FROM watch_history wh
                JOIN videos v ON v.id = wh.video_id
                WHERE 1=1 {extra_where}""",
            params
        )
        offset = (page - 1) * per_page

        rows = await db.fetch_all(
            f"""SELECT v.*, wh.watched_at as last_watched, wh.position as history_position,
                       wh.completed
                FROM videos v
                JOIN (
                    SELECT video_id, MAX(watched_at) as watched_at, position, completed
                    FROM watch_history GROUP BY video_id
                ) wh ON v.id = wh.video_id
                WHERE 1=1 {extra_where}
                ORDER BY wh.watched_at DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        )

        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            "videos": [self._row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    async def clear_watch_history(self):
        """Komplette Watch-History löschen."""
        await db.execute("DELETE FROM watch_history")
        await db.execute("UPDATE videos SET play_count = 0, last_played = NULL, last_position = 0")

    async def get_all_tags(self) -> list[dict]:
        """Alle verwendeten Tags mit Anzahl."""
        rows = await db.fetch_all(
            "SELECT tags FROM videos WHERE status = 'ready' AND tags != '[]'"
        )
        tag_count = {}
        for row in rows:
            try:
                tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"]
                for t in tags:
                    tag_count[t] = tag_count.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(
            [{"tag": t, "count": c} for t, c in tag_count.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

    async def get_stats(self) -> dict:
        """Statistiken abrufen."""
        video_count = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 0")
        total_size = await db.fetch_val("SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 0")
        total_duration = await db.fetch_val("SELECT COALESCE(SUM(duration), 0) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 0")
        streams_count = await db.fetch_val("SELECT COUNT(*) FROM streams")
        categories_count = await db.fetch_val("SELECT COUNT(*) FROM categories")
        favorites_count = await db.fetch_val("SELECT COUNT(*) FROM favorites")
        archives_count = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 1")
        playlists_count = await db.fetch_val("SELECT COUNT(*) FROM playlists")
        history_count = await db.fetch_val("SELECT COUNT(DISTINCT video_id) FROM watch_history")

        return {
            "video_count": video_count,
            "total_videos": video_count,
            "total_size_bytes": total_size,
            "total_duration_seconds": total_duration,
            "streams_count": streams_count,
            "categories_count": categories_count,
            "favorites_count": favorites_count,
            "archives_count": archives_count,
            "playlists_count": playlists_count,
            "history_count": history_count,
        }

    @staticmethod
    def _parse_multi_int(val: str) -> list[int]:
        """Komma-getrennter String zu int-Liste: '1,3,5' -> [1, 3, 5]"""
        result = []
        for v in val.split(","):
            v = v.strip()
            if v.isdigit():
                result.append(int(v))
        return result

    @staticmethod
    def _parse_multi_str(val: str) -> list[str]:
        """Komma-getrennter String zu String-Liste: 'a,b,c' -> ['a', 'b', 'c']"""
        return [v.strip() for v in val.split(",") if v.strip()]

    def _row_to_dict(self, row) -> dict:
        """DB Row in Dictionary konvertieren mit JSON-Parsing."""
        d = dict(row)
        for key in ("tags",):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        # AI-Felder entfernen falls noch in alter DB
        d.pop("ai_summary", None)
        d.pop("ai_tags", None)
        return d


# Singleton
metadata_service = MetadataService()
