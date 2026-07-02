"""
Tests für den Meta-Sidecar Service (Phase 5 – Meta-Redundanz).

Pin-Punkte:
- info.json entsteht NEBEN dem Video (videos_root/<id>/info.json)
- Inhalt ist pure Funktion der DB-Zeile: tags als echte Liste, keine
  Zeitstempel, keine Nutzerdaten (rating/play_count/notes)
- Idempotent: unveränderte Daten → kein zweites Schreiben
- Kein Ordner wird NEU angelegt (keine Leichen-Ordner für Platzhalter)
- Rebuild-Leser validiert sidecar_version + id
"""
import json

import pytest

from app.services import meta_sidecar


@pytest.fixture
def videos_root(tmp_path, monkeypatch):
    """Videos-Root auf ein Temp-Verzeichnis umbiegen (Storage liest ENV live)."""
    root = tmp_path / "videos"
    root.mkdir()
    monkeypatch.setenv("TUBEVAULT_VIDEOS_ROOT", str(root))
    return root


async def _insert_video(db, vid="testvid0001", **extra):
    cols = {
        "id": vid, "title": "Test Video", "channel_id": "UCabc",
        "channel_name": "Kanal", "duration": 123, "status": "ready",
        "tags": json.dumps(["a", "b"]), "view_count": 42,
        "source": "youtube", "video_type": "video",
        "rating": 5, "play_count": 9, "notes": "geheim",
    }
    cols.update(extra)
    names = ", ".join(cols)
    ph = ", ".join("?" * len(cols))
    await db.execute(f"INSERT INTO videos ({names}) VALUES ({ph})",
                     tuple(cols.values()))
    return vid


class TestPayload:
    async def test_tags_als_liste_und_keine_nutzerdaten(self, test_db):
        vid = await _insert_video(test_db)
        row = await test_db.fetch_one("SELECT * FROM videos WHERE id=?", (vid,))
        p = meta_sidecar.build_payload(row)
        assert p["sidecar_version"] == 1
        assert p["tags"] == ["a", "b"]
        assert p["title"] == "Test Video"
        # Nutzerdaten und Zeitstempel gehören NICHT ins Sidecar
        for verboten in ("rating", "play_count", "notes", "exported_at",
                         "created_at", "updated_at", "status"):
            assert verboten not in p

    async def test_kaputte_tags_fallback_kommaliste(self, test_db):
        vid = await _insert_video(test_db, vid="testvid0002", tags="rock, pop")
        row = await test_db.fetch_one("SELECT * FROM videos WHERE id=?", (vid,))
        assert meta_sidecar.build_payload(row)["tags"] == ["rock", "pop"]


class TestWrite:
    async def test_schreibt_neben_das_video(self, test_db, videos_root):
        vid = await _insert_video(test_db)
        (videos_root / vid).mkdir()
        res = await meta_sidecar.write_sidecar(vid)
        assert res == {"written": True}
        data = json.loads((videos_root / vid / "info.json").read_text("utf-8"))
        assert data["id"] == vid
        assert data["tags"] == ["a", "b"]

    async def test_idempotent_bei_unveraenderten_daten(self, test_db, videos_root):
        vid = await _insert_video(test_db)
        (videos_root / vid).mkdir()
        await meta_sidecar.write_sidecar(vid)
        res2 = await meta_sidecar.write_sidecar(vid)
        assert res2.get("skipped") and res2["reason"] == "unverändert"

    async def test_aenderung_schreibt_neu(self, test_db, videos_root):
        vid = await _insert_video(test_db)
        (videos_root / vid).mkdir()
        await meta_sidecar.write_sidecar(vid)
        await test_db.execute("UPDATE videos SET title='Neu' WHERE id=?", (vid,))
        res = await meta_sidecar.write_sidecar(vid)
        assert res == {"written": True}
        data = json.loads((videos_root / vid / "info.json").read_text("utf-8"))
        assert data["title"] == "Neu"

    async def test_legt_keinen_ordner_an(self, test_db, videos_root):
        vid = await _insert_video(test_db)  # kein Ordner erstellt
        res = await meta_sidecar.write_sidecar(vid)
        assert res.get("skipped") and "Ordner" in res["reason"]
        assert not (videos_root / vid).exists()

    async def test_unbekanntes_video(self, test_db, videos_root):
        assert await meta_sidecar.write_sidecar("gibtsnicht01") == {"missing": True}


class TestReadUndBackfill:
    async def test_read_roundtrip(self, test_db, videos_root):
        vid = await _insert_video(test_db)
        (videos_root / vid).mkdir()
        await meta_sidecar.write_sidecar(vid)
        data = await meta_sidecar.read_sidecar(vid)
        assert data["id"] == vid and data["sidecar_version"] == 1

    def test_read_validiert_fremde_jsons(self, tmp_path):
        p = tmp_path / "info.json"
        p.write_text('{"title": "yt-dlp style ohne version"}', encoding="utf-8")
        assert meta_sidecar.read_sidecar_file(p) is None
        p.write_text("kein json", encoding="utf-8")
        assert meta_sidecar.read_sidecar_file(p) is None

    async def test_backfill_schreibt_nur_vorhandene_ordner(self, test_db, videos_root):
        v1 = await _insert_video(test_db, vid="backfill0001")
        v2 = await _insert_video(test_db, vid="backfill0002")
        await _insert_video(test_db, vid="backfill0003", status="pending")
        (videos_root / v1).mkdir()  # nur v1 hat einen Ordner
        res = await meta_sidecar.backfill_sidecars(throttle_every=0)
        assert res["total"] == 2          # nur ready-Videos
        assert res["written"] == 1        # v1
        assert res["skipped"] == 1        # v2: kein Ordner
        assert (videos_root / v1 / "info.json").exists()
        assert not (videos_root / v2).exists()

    async def test_status_zaehlt(self, test_db, videos_root):
        vid = await _insert_video(test_db, vid="statuscnt001")
        (videos_root / vid).mkdir()
        await meta_sidecar.write_sidecar(vid)
        st = await meta_sidecar.sidecar_status()
        assert st["videos_ready"] == 1
        assert st["sidecars_present"] == 1
        assert st["sidecars_missing"] == 0
