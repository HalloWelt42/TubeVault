"""
TubeVault – Metadata Service v1.3.0
© HalloWelt42 – Private Nutzung
"""

import json
import logging
from datetime import datetime

from app.database import db
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags

logger = logging.getLogger(__name__)

# Grund auf der Ignorierliste für vom Nutzer gelöschte Videos
MANUALLY_DELETED = "manuell gelöscht"


class MetadataService:
    """Video-Metadaten verwalten und anreichern."""

    async def get_video(self, video_id: str) -> dict | None:
        """Einzelnes Video mit allen Details abrufen."""
        row = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not row:
            return None
        result = self._row_to_dict(row)
        # description kommt immer über den Resolver (File-first, DB-Fallback)
        from app.services.text_resolver import get_description
        result["description"] = await get_description(video_id) or ""
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
        sort_by: str = "upload_date",
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

        if search and search.strip():
            # Gleiche Regeln wie die globale Suche (eine Wahrheit, siehe search_index)
            from app.services import search_index
            await search_index.refresh_before_query()
            search_sql, search_params = search_index.condition(search, "v")
            conditions.append(search_sql)
            params.extend(search_params)

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

        # Shorts global ausgeschlossen?
        from app.services import video_classifier
        shorts_clause = await video_classifier.without_shorts("v")
        if shorts_clause:
            conditions.append(shorts_clause.removeprefix(" AND "))

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
            "is_favorite",  # virtuell via EXISTS-Subquery auf favorites-Tabelle
        }
        if sort_by not in allowed_sorts:
            sort_by = "created_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        # ORDER BY – is_favorite ist virtuell und wird via EXISTS gebaut.
        # Tiebreaker created_at DESC, damit neue Videos bei gleichem
        # Sortierwert oben bleiben (wichtig bei NULL-Feldern wie upload_date).
        # v.id als letzter Schlüssel macht die Reihenfolge eindeutig: ohne ihn
        # ist sie bei Gleichstand (hunderte Videos mit demselben Upload-Tag)
        # zufällig, und seitenweises Nachladen liefert Videos doppelt oder nie.
        if sort_by == "is_favorite":
            order_by = (
                f"(EXISTS (SELECT 1 FROM favorites f WHERE f.video_id = v.id)) {order}, "
                f"v.created_at DESC, v.id"
            )
        else:
            # NULLs ans Ende bei DESC, sonst stehen unbekannte Upload-Daten oben
            null_placement = "NULLS LAST" if order == "DESC" else "NULLS FIRST"
            order_by = f"v.{sort_by} {order} {null_placement}, v.created_at DESC, v.id"

        # Total Count
        total = await db.fetch_val(f"SELECT COUNT(*) FROM videos v {where}", params)

        # Paginierte Ergebnisse
        offset = (page - 1) * per_page
        rows = await db.fetch_all(
            f"""SELECT v.* FROM videos v {where}
                ORDER BY {order_by}
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

            if "description" in filtered:
                try:
                    from app.services import text_export
                    await text_export.export_description(video_id)
                except Exception as e:
                    logger.warning(f"text_export description {video_id}: {e}")

        # Typ von Hand gesetzt: gilt auch für den Feed und bleibt vor der
        # automatischen Prüfung geschützt
        if "video_type" in filtered:
            from app.services import video_classifier
            await video_classifier.set_manual([video_id], filtered["video_type"])

        # Meta-Redundanz: Sidecar nachziehen (idempotent, wirft nie)
        from app.services import meta_sidecar
        await meta_sidecar.write_sidecar(video_id)

        return await self.get_video(video_id)

    # Alles, was an einem Video hängt. Löschen heisst: nichts davon bleibt.
    # (Tabelle, Spalte) - jede Zeile mit dieser Video-ID wird entfernt.
    _VIDEO_ROWS = (
        ("video_categories", "video_id"),
        ("favorites", "video_id"),
        ("playlist_videos", "video_id"),
        ("watch_history", "video_id"),
        ("streams", "video_id"),
        ("stream_combinations", "video_id"),
        ("chapters", "video_id"),
        ("ad_markers", "video_id"),
        ("video_links", "video_id"),
        ("video_links", "linked_video_id"),
        ("enrichment_log", "video_id"),
        ("text_files", "video_id"),
        ("audio_tracks", "video_id"),
        ("dub_requests", "video_id"),
    )

    @staticmethod
    def _video_locations(video_id: str) -> list:
        """Alle Ordner, in denen TubeVault Dateien zu einem Video ablegt."""
        from app import config
        from app.services.storage import storage
        return [
            config.VIDEOS_DIR / video_id,
            config.THUMBNAILS_DIR / video_id,
            config.SUBTITLES_DIR / video_id,
            config.AUDIO_DIR / video_id,
            config.METADATA_DIR / video_id,
            config.DATA_DIR / "chapter_thumbs" / video_id,
            storage.video_dir(video_id),
        ]

    async def delete_video(self, video_id: str, ignore_for_future: bool = True) -> bool:
        """Video restlos löschen - danach ist es, als wäre es nie geladen worden:
        keine Dateien (Video, Vorschaubilder, Untertitel, Tonspuren, Texte,
        Kapitelbilder), keine Zeilen in abhängigen Tabellen, kein Treffer in
        der Suche. Im Feed steht es wieder als nicht geladen.

        ignore_for_future=True (Standard): Das Video kommt auf die Ignorierliste,
        damit Auto-Download und Drip es nicht von selbst wieder holen. Von Hand
        lässt es sich jederzeit erneut laden (das hebt den Eintrag auf).
        Dateien ausserhalb des Datenordners (z.B. Originale importierter
        eigener Videos) werden nicht angefasst."""
        import shutil
        from pathlib import Path
        from app import config

        video = await self.get_video(video_id)
        if not video:
            return False

        for location in self._video_locations(video_id):
            if location.exists():
                shutil.rmtree(location, ignore_errors=True)
        # Einzeldatei, die im Datenordner, aber nicht im Video-Ordner liegt
        file_path = video.get("file_path")
        if file_path:
            path = Path(file_path)
            try:
                inside = path.resolve().is_relative_to(config.DATA_DIR.resolve())
            except OSError:
                inside = False
            if inside and path.is_file():
                path.unlink(missing_ok=True)

        for table, column in self._VIDEO_ROWS:
            await db.execute(f"DELETE FROM {table} WHERE {column} = ?", (video_id,))
        await db.execute(
            "DELETE FROM jobs WHERE type='download' AND json_extract(metadata, '$.video_id') = ?",
            (video_id,))
        # Feed-Katalog bleibt, zeigt das Video aber wieder als nicht geladen
        await db.execute(
            "UPDATE rss_entries SET status = 'new', auto_queued = 0 WHERE video_id = ?", (video_id,))

        if ignore_for_future:
            await db.execute(
                """INSERT OR IGNORE INTO ignored_videos (video_id, channel_id, reason)
                   VALUES (?, ?, ?)""",
                (video_id, video.get("channel_id"), MANUALLY_DELETED),
            )

        # Video selbst löschen (der Suchindex zieht per Trigger nach)
        await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))

        await db.execute(
            """UPDATE playlists SET video_count = (
                SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = playlists.id
            )"""
        )

        logger.info(f"Video restlos gelöscht: {video_id}"
                    + (" (auf Ignorierliste für automatische Downloads)" if ignore_for_future else ""))
        return True

    async def delete_channel_videos(self, channel_id: str) -> int:
        """Alle Videos eines Kanals restlos löschen. Ohne Ignorierliste: der
        Kanal wird ohnehin entfernt, ein späteres neues Abo soll frei laden."""
        rows = await db.fetch_all("SELECT id FROM videos WHERE channel_id = ?", (channel_id,))
        deleted = 0
        for row in rows:
            if await self.delete_video(row["id"], ignore_for_future=False):
                deleted += 1
        return deleted

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
        from app.services import video_classifier
        extra_where += await video_classifier.without_shorts("v")

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
                ORDER BY wh.watched_at DESC, v.id
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

    async def get_all_tags(
        self,
        video_type: str = None,
        video_types: str = None,
        channel_ids: str = None,
        category_ids: str = None,
        is_archived: bool = False,
    ) -> list[dict]:
        """Tags aggregieren — optional gefiltert auf dieselben Kriterien
        wie /api/videos. Damit zeigt der Tag-Filter nur Tags der aktuell
        sichtbaren Liste (keine globalen 64k Tags mehr).

        Args:
          video_type:   'video' | 'short' | 'live' | 'music' | None
          video_types:  komma-getrennte Typ-Liste (hat Vorrang vor video_type)
          channel_ids:  komma-getrennte channel_id-Liste
          category_ids: komma-getrennte category_id-Liste (M2M über video_categories)
          is_archived:  True → nur archivierte, False → nur nicht-archivierte
        """
        conditions = ["status = 'ready'", "tags != '[]'"]
        params: list = []

        if is_archived:
            conditions.append("COALESCE(is_archived, 0) = 1")
        else:
            conditions.append("COALESCE(is_archived, 0) = 0")

        if video_types:
            vtypes = [v.strip() for v in video_types.split(",") if v.strip()]
            if vtypes:
                placeholders = ",".join("?" * len(vtypes))
                conditions.append(f"COALESCE(video_type, 'video') IN ({placeholders})")
                params.extend(vtypes)
        elif video_type == "music":
            conditions.append("is_music = 1")
        elif video_type in ("video", "short", "live"):
            conditions.append("COALESCE(video_type, 'video') = ?")
            params.append(video_type)

        if channel_ids:
            cids = [c.strip() for c in channel_ids.split(",") if c.strip()]
            if cids:
                placeholders = ",".join("?" * len(cids))
                conditions.append(f"channel_id IN ({placeholders})")
                params.extend(cids)

        if category_ids:
            catids = [c.strip() for c in category_ids.split(",") if c.strip()]
            if catids:
                placeholders = ",".join("?" * len(catids))
                conditions.append(
                    f"id IN (SELECT video_id FROM video_categories WHERE category_id IN ({placeholders}))"
                )
                params.extend(catids)

        from app.services import video_classifier
        where = " AND ".join(conditions) + await video_classifier.without_shorts()
        rows = await db.fetch_all(f"SELECT tags FROM videos WHERE {where}", tuple(params))

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
        """Statistiken abrufen. Zählungen zentral aus counts_service
        (eine Quelle der Wahrheit), Response-Shape unverändert."""
        from app.services.counts_service import counts_service as cs
        video_count = await cs.library_videos()
        total_size = await cs.library_size_bytes()
        total_duration = await cs.library_duration_seconds()
        streams_count = await cs.streams()
        categories_count = await cs.categories()
        favorites_count = await cs.favorites()
        archives_count = await cs.archived_videos()
        playlists_count = await cs.playlists_total()
        history_count = await cs.history_entries()

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
