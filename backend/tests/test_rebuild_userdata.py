"""
Tests für Userdata-Export + Offline-Rebuild (Phase 5 – Meta-Redundanz).

Pin-Punkte:
- Export schreibt JSONL pro Tabelle + manifest.json mit Zählern
- Rotation behält nur die letzten KEEP Exporte
- Restore: INSERT OR IGNORE (vorhandene Zeilen gewinnen), Video-Nutzerfelder
  überschreiben keine frischeren Werte
- Musik (16.10.2026): Lieblingssong, Wiedergaben und Ausgeblendetes der eigenen
  Sammlung, Hörbuch-Stand, Musikkanäle und die Hörbuch-Wahl an Videos kommen
  mit; fehlt eine Datei noch in der Tabelle, entsteht ihr Eintrag aus der
  Sicherung (das nächste Einlesen ergänzt den Rest)
- Rebuild stellt gelöschte videos-Zeilen aus Sidecars wieder her,
  findet die Mediendatei (auch video_tmp.*) und liest description aus TEXTS
- dry_run zählt nur, schreibt nichts
"""
import json

import pytest

from app.services import meta_sidecar, rebuild_service, userdata_export


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Alle Storage-Roots auf Temp umbiegen."""
    for env, sub in [("TUBEVAULT_VIDEOS_ROOT", "videos"),
                     ("TUBEVAULT_EXPORTS_ROOT", "exports"),
                     ("TUBEVAULT_TEXTS_ROOT", "texts")]:
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(env, str(tmp_path / sub))
    return tmp_path


async def _seed(db, vid="rebuild00001"):
    await db.execute(
        """INSERT INTO videos (id, title, channel_name, duration, status,
           tags, rating, play_count, source, video_type)
           VALUES (?, 'Original', 'Kanal', 99, 'ready', '["x"]', 4, 7,
                   'youtube', 'video')""", (vid,))
    await db.execute(
        "INSERT INTO favorites (video_id, list_name) VALUES (?, 'default')", (vid,))
    await db.execute(
        "INSERT INTO watch_history (video_id, position, completed) VALUES (?, 12, 0)",
        (vid,))
    await db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCx', 'Abo')")
    return vid


class TestExport:
    async def test_export_schreibt_jsonl_und_manifest(self, test_db, roots):
        await _seed(test_db)
        res = await userdata_export.export_userdata()
        folder = userdata_export.userdata_root() / res["folder"]
        assert (folder / "favorites.jsonl").exists()
        assert (folder / "video_userdata.jsonl").exists()
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        assert manifest["counts"]["favorites"] == 1
        assert manifest["counts"]["watch_history"] == 1
        assert manifest["counts"]["subscriptions"] == 1
        assert manifest["counts"]["video_userdata"] == 1  # rating+play_count gesetzt

    async def test_rotation_behaelt_nur_keep(self, test_db, roots):
        root = userdata_export.userdata_root()
        root.mkdir(parents=True, exist_ok=True)
        for i in range(20):
            (root / f"userdata_2000010{i:02d}_000000").mkdir()
        await userdata_export.export_userdata()
        dirs = [d for d in root.iterdir() if d.is_dir()]
        assert len(dirs) == userdata_export.KEEP_EXPORTS

    async def test_list_exports(self, test_db, roots):
        await _seed(test_db)
        await userdata_export.export_userdata()
        lst = userdata_export.list_exports()
        assert len(lst) == 1 and lst[0]["counts"]["favorites"] == 1


class TestRestore:
    async def test_restore_bringt_geloeschte_daten_zurueck(self, test_db, roots):
        vid = await _seed(test_db)
        await userdata_export.export_userdata()
        # Datenverlust simulieren (rating-Default ist 0 = unbewertet, nicht NULL)
        await test_db.execute("DELETE FROM favorites")
        await test_db.execute(
            "UPDATE videos SET rating=0, play_count=0 WHERE id=?", (vid,))
        res = await rebuild_service.restore_userdata()
        assert res["tables"]["favorites"]["inserted"] == 1
        row = await test_db.fetch_one(
            "SELECT rating, play_count FROM videos WHERE id=?", (vid,))
        assert row["rating"] == 4 and row["play_count"] == 7

    async def test_restore_ueberschreibt_keine_frischeren_werte(self, test_db, roots):
        vid = await _seed(test_db)
        await userdata_export.export_userdata()
        await test_db.execute("UPDATE videos SET rating=2 WHERE id=?", (vid,))
        await rebuild_service.restore_userdata()
        row = await test_db.fetch_one("SELECT rating FROM videos WHERE id=?", (vid,))
        assert row["rating"] == 2  # COALESCE: vorhandener Wert gewinnt

    async def test_musik_und_hoerbuecher_kommen_mit(self, test_db, roots):
        await test_db.execute(
            """INSERT INTO music_files (id, path, title, artist, size, mtime, favorite, play_count, hidden, hidden_at) VALUES
               ('f111111111111111', 'A/lieb.flac', 'Lieb', 'Band', 10, 1.0, 1, 3, 0, NULL),
               ('f222222222222222', 'A/weg.flac', 'Weg', 'Band', 10, 1.0, 0, 0, 1, '2026-10-16 10:00:00'),
               ('f333333333333333', 'A/egal.flac', 'Egal', 'Band', 10, 1.0, 0, 0, 0, NULL)""")
        await test_db.execute("INSERT INTO audiobook_progress (book, file_id, position) VALUES ('insel', 'f111111111111111', 42)")
        await test_db.execute("INSERT INTO music_channels (channel_id) VALUES ('UCmusik')")
        await test_db.execute(
            """INSERT INTO videos (id, title, status, is_audiobook, audiobook_source)
               VALUES ('hoerspiel01', 'Folge 1', 'ready', 1, 'user')""")
        manifest = await userdata_export.export_userdata()
        assert manifest["counts"]["music_file_userdata"] == 2          # nur Zeilen mit Nutzerdaten

        await test_db.execute("DELETE FROM music_files WHERE id <> 'f111111111111111'")
        await test_db.execute("UPDATE music_files SET play_count = 9, favorite = 0 WHERE id = 'f111111111111111'")
        for table in ("audiobook_progress", "music_channels"):
            await test_db.execute(f"DELETE FROM {table}")
        await test_db.execute("UPDATE videos SET is_audiobook = 0, audiobook_source = NULL WHERE id = 'hoerspiel01'")

        res = await rebuild_service.restore_userdata()
        assert res["tables"]["music_file_userdata"]["rows"] == 2
        lieb = await test_db.fetch_one("SELECT favorite, play_count FROM music_files WHERE id = 'f111111111111111'")
        assert (lieb["favorite"], lieb["play_count"]) == (1, 9)          # frischere Wiedergaben bleiben
        weg = await test_db.fetch_one("SELECT path, title, hidden, size FROM music_files WHERE id = 'f222222222222222'")
        assert (weg["path"], weg["title"], weg["hidden"], weg["size"]) == ("A/weg.flac", "Weg", 1, None)
        assert await test_db.fetch_val("SELECT position FROM audiobook_progress WHERE book = 'insel'") == 42
        assert await test_db.fetch_val("SELECT COUNT(*) FROM music_channels") == 1
        video = await test_db.fetch_one("SELECT is_audiobook, audiobook_source FROM videos WHERE id = 'hoerspiel01'")
        assert (video["is_audiobook"], video["audiobook_source"]) == (1, "user")

    async def test_restore_ohne_export(self, test_db, roots):
        res = await rebuild_service.restore_userdata()
        assert "error" in res


class TestRebuild:
    async def _make_sidecar_folder(self, test_db, roots, vid):
        vdir = roots / "videos" / vid
        vdir.mkdir()
        (vdir / "video_tmp.mkv").write_bytes(b"x" * 100)  # Altlast-Name
        (vdir / "video.mp4").write_bytes(b"x" * 500)      # größer → gewinnt
        await meta_sidecar.write_sidecar(vid)
        return vdir

    async def test_rebuild_stellt_geloeschtes_video_wieder_her(self, test_db, roots):
        vid = await _seed(test_db)
        await self._make_sidecar_folder(test_db, roots, vid)
        (roots / "texts" / vid).mkdir()
        (roots / "texts" / vid / "description.txt").write_text("Beschreibung!", "utf-8")
        await test_db.execute("DELETE FROM videos WHERE id=?", (vid,))

        res = await rebuild_service.rebuild_from_sidecars(throttle_every=0)
        assert res["restored"] == 1
        row = await test_db.fetch_one("SELECT * FROM videos WHERE id=?", (vid,))
        assert row["title"] == "Original"
        assert row["status"] == "ready"
        assert row["file_path"].endswith("video.mp4")  # größte Datei gewonnen
        assert row["file_size"] == 500
        # Die Beschreibung bleibt in ihrer Datei (Inhalte als Datei), die Spalte leer
        assert row["description"] is None
        from app.services import text_resolver
        assert await text_resolver.get_description(vid) == "Beschreibung!"
        assert json.loads(row["tags"]) == ["x"]

    async def test_rebuild_laesst_bestehende_in_ruhe(self, test_db, roots):
        vid = await _seed(test_db)
        await self._make_sidecar_folder(test_db, roots, vid)
        res = await rebuild_service.rebuild_from_sidecars(throttle_every=0)
        assert res["existing"] == 1 and res["restored"] == 0
        row = await test_db.fetch_one("SELECT title FROM videos WHERE id=?", (vid,))
        assert row["title"] == "Original"

    async def test_dry_run_schreibt_nichts(self, test_db, roots):
        vid = await _seed(test_db)
        await self._make_sidecar_folder(test_db, roots, vid)
        await test_db.execute("DELETE FROM videos WHERE id=?", (vid,))
        res = await rebuild_service.rebuild_from_sidecars(dry_run=True, throttle_every=0)
        assert res["restored"] == 1
        assert await test_db.fetch_one("SELECT id FROM videos WHERE id=?", (vid,)) is None

    async def test_ordner_ohne_sidecar_oder_media(self, test_db, roots):
        (roots / "videos" / "ohnesidecar1").mkdir()
        (roots / "videos" / "ohnemedia001").mkdir()
        (roots / "videos" / "ohnemedia001" / "info.json").write_text(
            json.dumps({"sidecar_version": 1, "id": "ohnemedia001"}), "utf-8")
        res = await rebuild_service.rebuild_from_sidecars(throttle_every=0)
        assert res["invalid"] == 1
        assert res["no_media"] == 1
        assert res["restored"] == 0
