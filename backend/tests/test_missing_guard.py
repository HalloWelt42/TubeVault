"""Schutz bei nicht erreichbarem Bestand (NETZ-28): Fehlt ein Laufwerk, wird nichts als fehlend markiert oder
ausgetragen, und ohne Datenbank legt TubeVault keine neue an."""
import pytest

from app.services import ghost_videos, missing_guard, music_files, own_inventory, own_scan


# ─── Regel ─────────────────────────────────────────────────────────────

def test_regel_einzelne_fehlende_sind_echt(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert missing_guard.judge(0, 1000, [tmp_path], "Probe").allowed
    assert missing_guard.judge(missing_guard.ALWAYS_ALLOWED, 1000, [tmp_path], "Probe").allowed
    assert missing_guard.judge(20, 1000, [tmp_path], "Probe").allowed


def test_regel_viel_auf_einmal_ist_ein_laufwerk(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    verdict = missing_guard.judge(500, 1000, [tmp_path], "Probe")
    assert not verdict.allowed and "500 von 1000" in verdict.reason


def test_regel_leerer_oder_fehlender_ordner(tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    assert not missing_guard.judge(1, 10, [leer], "Probe").allowed
    assert not missing_guard.judge(1, 10, [tmp_path / "fehlt"], "Probe").allowed
    assert not missing_guard.root_reachable(leer)
    assert not missing_guard.root_reachable(tmp_path / "fehlt")


# ─── Videos ohne Datei ─────────────────────────────────────────────────

@pytest.fixture
def medien(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    videos.mkdir()
    monkeypatch.setattr(ghost_videos, "MEDIA_ROOTS", (videos, tmp_path / "audio"))
    return videos


async def _videos(db, videos, anzahl, mit_datei):
    for i in range(anzahl):
        datei = videos / f"v{i}.mp4"
        if i < mit_datei:
            datei.write_bytes(b"\x00" * 2048)
        await db.execute("INSERT INTO videos (id, title, file_path, status) VALUES (?, ?, ?, 'ready')",
                         (f"v{i}", f"Video {i}", str(datei)))


async def _status(db):
    rows = await db.fetch_all("SELECT status, COUNT(*) AS n FROM videos GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


async def test_einzelnes_video_ohne_datei_wird_ghost(test_db, medien):
    await _videos(test_db, medien, 100, mit_datei=99)
    result = await ghost_videos.mark_ghosts()
    assert (result.found, result.marked, result.blocked_reason) == (1, 1, "")
    assert await _status(test_db) == {"ready": 99, "ghost": 1}


async def test_bestand_weg_kein_video_wird_ghost(test_db, medien):
    await _videos(test_db, medien, 100, mit_datei=100)
    for datei in medien.iterdir():      # Laufwerk weg: Einhängepunkt leer
        datei.unlink()
    result = await ghost_videos.mark_ghosts()
    assert result.marked == 0 and "nicht erreichbar" in result.blocked_reason
    assert await _status(test_db) == {"ready": 100}


async def test_halber_bestand_kein_video_wird_ghost(test_db, medien):
    await _videos(test_db, medien, 100, mit_datei=40)
    result = await ghost_videos.mark_ghosts()
    assert (result.found, result.marked) == (60, 0) and "60 von 100" in result.blocked_reason
    assert await _status(test_db) == {"ready": 100}


async def test_ausdruecklich_trotzdem_markieren(test_db, medien):
    await _videos(test_db, medien, 100, mit_datei=40)
    result = await ghost_videos.mark_ghosts(force=True)
    assert result.marked == 60
    assert await _status(test_db) == {"ready": 40, "ghost": 60}


# ─── Musiksammlung ─────────────────────────────────────────────────────

async def _lieder(db, anzahl):
    for i in range(anzahl):
        await db.execute("INSERT INTO music_files (id, path, size, mtime) VALUES (?, ?, 1, 1)", (f"f{i}", f"lied{i}.flac"))


async def test_musik_laufwerk_halb_weg_nichts_ausgetragen(test_db, tmp_path, monkeypatch):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "cover.jpg").write_bytes(b"x")      # erreichbar, aber die Lieder fehlen alle
    monkeypatch.setattr(music_files, "MUSIC_FILES_DIR", root)
    await _lieder(test_db, 100)
    result = await music_files.scan()
    assert result.removed == 0
    assert await test_db.fetch_val("SELECT COUNT(*) FROM music_files") == 100


async def test_musik_einzelne_geloeschte_lieder_werden_ausgetragen(test_db, tmp_path, monkeypatch):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "cover.jpg").write_bytes(b"x")
    monkeypatch.setattr(music_files, "MUSIC_FILES_DIR", root)
    await _lieder(test_db, 3)
    result = await music_files.scan()
    assert result.removed == 3
    assert await test_db.fetch_val("SELECT COUNT(*) FROM music_files") == 0


# ─── Eigene Videos ─────────────────────────────────────────────────────

def _gelistet(anzahl):
    return [own_inventory.ListedFile(rel_path=f"ARTE/v{i}.mp4", size=10, mtime=1.0) for i in range(anzahl)]


async def test_eigene_videos_laufwerk_weg_nichts_verschwindet(test_db, tmp_path, monkeypatch):
    root = tmp_path / "sammlung"
    root.mkdir()
    monkeypatch.setattr(own_scan, "collection_root", lambda: root)
    await own_scan._sync("", _gelistet(100))
    await own_scan._sync("", [])        # Auflisten fand nichts, der Ordner ist leer
    assert await test_db.fetch_val("SELECT COUNT(*) FROM own_files WHERE present = 1") == 100


async def test_eigene_videos_einzeln_entfernt_gilt_als_verschwunden(test_db, tmp_path, monkeypatch):
    root = tmp_path / "sammlung"
    (root / "ARTE").mkdir(parents=True)
    monkeypatch.setattr(own_scan, "collection_root", lambda: root)
    await own_scan._sync("", _gelistet(100))
    await own_scan._sync("", _gelistet(99))
    assert await test_db.fetch_val("SELECT COUNT(*) FROM own_files WHERE present = 0") == 1


# ─── Datenbank ─────────────────────────────────────────────────────────

async def test_ohne_datenbank_kein_neuanlegen(tmp_path):
    from app.database import Database
    db = Database(db_path=tmp_path / "db" / "tubevault.db")
    with pytest.raises(SystemExit, match="legt keine neue an"):
        await db.connect()
    assert not (tmp_path / "db" / "tubevault.db").exists()


async def test_marke_erlaubt_neuanlegen_einmal(tmp_path):
    from app.database import Database, NEU_EINRICHTEN_MARKE
    ordner = tmp_path / "db"
    ordner.mkdir()
    (ordner / NEU_EINRICHTEN_MARKE).touch()
    db = Database(db_path=ordner / "tubevault.db")
    await db.connect()
    await db.disconnect()
    assert (ordner / "tubevault.db").exists()
    assert not (ordner / NEU_EINRICHTEN_MARKE).exists()


async def test_vorhandene_datenbank_oeffnet_ohne_marke(tmp_path):
    from app.database import Database
    pfad = tmp_path / "tubevault.db"
    erste = Database(db_path=pfad, allow_create=True)
    await erste.connect()
    await erste.disconnect()
    zweite = Database(db_path=pfad)
    await zweite.connect()
    await zweite.disconnect()
