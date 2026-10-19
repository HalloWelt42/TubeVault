"""
Sammlungen, Stand und Verlauf (Wunsch 15.10.2026: Favoriten, Playlists und
Verlauf deutlich besser bedienbar).

Kontrakt:
- Stand je Video allein aus gemerkter Stelle und Dauer: neu, angefangen, gesehen;
  SQL und Python urteilen gleich.
- Favoritenlisten und Playlists kommen einheitlich als Sammlung mit Stand.
- Als gesehen / als neu markieren setzt die gemerkte Stelle.
- Favoriten lassen sich in eine (neue) Liste verschieben.
- Playlist-Übersicht: Bild aus den ersten drei Videos, gesehen/angefangen, Kopie.
- Verlauf: nach Stand und Zeitraum filtern, einzeln entfernen, ältere leeren,
  gemerkte Stellen bleiben; pausiert wird nichts mitgeschrieben.
- Jede Sammlung lässt sich ganz als Ton abspielen, auch Nicht-Musik.
"""
import pytest

from app.routers import collections as collections_router, favorites, playlists
from app.services import collections, music_library, watch_state
from app.services.metadata_service import metadata_service


async def _video(db, vid, title, position=0, duration=600, is_music=0, channel="Kanal"):
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, duration, last_position, is_music, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'ready')""", (vid, title, "UC" + channel, channel, duration, position, is_music))


async def _bestand(db):
    await _video(db, "neu00000001", "Ganz neu")
    await _video(db, "angef000001", "Halb gesehen", position=300)
    await _video(db, "fertig00001", "Zu Ende", position=590)
    await _video(db, "angetippt01", "Nur angetippt", position=3)
    for pos, vid in enumerate(["fertig00001", "neu00000001", "angef000001"]):
        await db.execute("INSERT INTO favorites (video_id, list_name, position) VALUES (?, 'Standard', ?)", (vid, pos))
    cursor = await db.execute("INSERT INTO playlists (name) VALUES ('Lernen')")
    for pos, vid in enumerate(["angef000001", "angetippt01", "fertig00001", "neu00000001"]):
        await db.execute("INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
                         (cursor.lastrowid, vid, pos))
    return cursor.lastrowid


@pytest.mark.parametrize("position, duration, state", [
    (0, 600, "new"), (5, 600, "new"), (6, 600, "started"), (569, 600, "started"),
    (570, 600, "finished"), (700, 600, "finished"), (100, 0, "new"), (None, None, "new")])
def test_stand_aus_stelle_und_dauer(position, duration, state):
    assert watch_state.state_of(position, duration) == state


async def test_stand_in_sql_wie_in_python(test_db):
    await _bestand(test_db)
    rows = await test_db.fetch_all(f"SELECT id, last_position, duration, {watch_state.state_sql('v')} AS s FROM videos v")
    assert all(r["s"] == watch_state.state_of(r["last_position"], r["duration"]) for r in rows)


async def test_favoriten_als_sammlung(test_db):
    await _bestand(test_db)
    favs = await collections.load("favorites:Standard")
    assert favs.title == "Favoriten" and [i.id for i in favs.items] == ["fertig00001", "neu00000001", "angef000001"]
    assert favs.counts == {"new": 1, "started": 1, "finished": 1, "pending": 0} and favs.duration == 1800
    assert favs.items[2].state == "started" and favs.items[2].progress == 0.5


async def test_playlist_als_sammlung_und_unbekanntes(test_db):
    pl = await _bestand(test_db)
    lernen = await collections.load(f"playlist:{pl}")
    assert lernen.title == "Lernen" and lernen.items[1].state == "new"   # angetippt zählt nicht
    with pytest.raises(LookupError):
        await collections.load("playlist:999")
    with pytest.raises(ValueError):
        await collections.load("irgendwas:1")


async def test_als_gesehen_und_als_neu(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(collections_router.router) as client:
        r = await client.post("/api/collections/watched", json={"video_ids": ["neu00000001"], "watched": True})
        assert r.json()["changed"] == 1
        await client.post("/api/collections/watched", json={"video_ids": ["angef000001"], "watched": False})
    favs = await collections.load("favorites:Standard")
    assert {i.id: i.state for i in favs.items} == {"fertig00001": "finished", "neu00000001": "finished", "angef000001": "new"}


async def test_favoriten_in_neue_liste_verschieben(test_db):
    await _bestand(test_db)
    await favorites.move_favorites(favorites.FavoriteMove(
        video_ids=["neu00000001", "angef000001"], from_list="Standard", to_list="Später"))
    assert [i.id for i in (await collections.load("favorites:Später")).items] == ["neu00000001", "angef000001"]
    assert [i.id for i in (await collections.load("favorites:Standard")).items] == ["fertig00001"]


async def test_playlist_uebersicht_und_kopie(test_db):
    pl = await _bestand(test_db)
    eintrag = next(p for p in await playlists.get_playlists() if p["id"] == pl)
    assert eintrag["cover_ids"] == ["angef000001", "angetippt01", "fertig00001"]
    assert (eintrag["video_count"], eintrag["finished_count"], eintrag["started_count"]) == (4, 1, 1)
    kopie = await playlists.copy_playlist(pl)
    assert [i.id for i in (await collections.load(f"playlist:{kopie['id']}")).items] == \
           [i.id for i in (await collections.load(f"playlist:{pl}")).items]


async def _verlauf(db):
    await _bestand(db)
    await db.execute("INSERT INTO watch_history (video_id, position, watched_at) VALUES ('angef000001', 300, '2026-10-15 08:00:00')")
    await db.execute("INSERT INTO watch_history (video_id, position, watched_at) VALUES ('fertig00001', 590, '2026-10-01 20:00:00')")
    await db.execute("INSERT INTO watch_history (video_id, position, watched_at) VALUES ('neu00000001', 0, '2020-01-01 10:00:00')")


async def test_verlauf_nach_stand_und_zeitraum(test_db):
    await _verlauf(test_db)
    angefangen = await metadata_service.get_watch_history(state="started")
    assert [v["id"] for v in angefangen["videos"]] == ["angef000001"] and angefangen["total"] == 1
    assert angefangen["videos"][0]["state"] == "started" and angefangen["videos"][0]["progress"] == 0.5
    neuer = await metadata_service.get_watch_history(since="2026-10-01 00:00:00")
    assert [v["id"] for v in neuer["videos"]] == ["angef000001", "fertig00001"] and neuer["total"] == 2


async def test_verlauf_entfernen_und_leeren_behaelt_stellen(test_db):
    await _verlauf(test_db)
    entfernt = await metadata_service.remove_from_history("fertig00001")
    assert [e["watched_at"] for e in entfernt] == ["2026-10-01 20:00:00"]
    assert await metadata_service.restore_history("fertig00001", entfernt) == 1
    assert (await metadata_service.get_watch_history())["total"] == 3
    await metadata_service.remove_from_history("fertig00001")
    assert await metadata_service.clear_watch_history(older_than_days=30) == 1      # nur der von 2020
    assert [v["id"] for v in (await metadata_service.get_watch_history())["videos"]] == ["angef000001"]
    await metadata_service.clear_watch_history()
    assert (await metadata_service.get_watch_history())["total"] == 0
    assert await test_db.fetch_val("SELECT last_position FROM videos WHERE id = 'angef000001'") == 300


async def test_pausierter_verlauf_schreibt_nichts_merkt_aber_die_stelle(test_db):
    await _bestand(test_db)
    await test_db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('history.paused', 'true')")
    await metadata_service.record_play("neu00000001")
    await metadata_service.save_position("neu00000001", 120)
    assert await test_db.fetch_val("SELECT COUNT(*) FROM watch_history") == 0
    assert await test_db.fetch_val("SELECT last_position FROM videos WHERE id = 'neu00000001'") == 120


async def test_sammlung_ganz_als_ton(test_db):
    pl = await _bestand(test_db)
    await _video(test_db, "musik000001", "ABBA - Waterloo", is_music=1, channel="AbbaVEVO")
    await test_db.execute("INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (?, 'musik000001', 9)", (pl,))
    liste = await music_library.play_list(f"sammlung:playlist:{pl}")
    assert liste.title == "Lernen" and len(liste.tracks) == 5
    assert liste.tracks[0].title == "Halb gesehen" and liste.tracks[0].artist == "Kanal"
    assert liste.tracks[-1].artist == "ABBA" and liste.tracks[-1].title == "Waterloo"


async def test_playlist_mit_vorgemerkten_und_drip(test_db, monkeypatch):
    """Vorgemerkte (noch nicht geladene) Videos stehen in der Playlist, abspielbar
    ist nur Geladenes; der Drip reiht die nächsten fehlenden ein und schaltet
    sich ab, wenn nichts mehr fehlt."""
    from app.routers import playlists as playlists_router
    from app.services import drip
    pl = await _bestand(test_db)
    for pos, vid in enumerate(["fehlt000001", "fehlt000002", "fehlt000003"], start=10):
        await test_db.execute("INSERT INTO videos (id, title, status) VALUES (?, ?, 'bookmarked')", (vid, f"Fehlt {pos}"))
        await test_db.execute("INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)", (pl, vid, pos))
    lernen = await collections.load(f"playlist:{pl}")
    assert lernen.counts["pending"] == 3 and len(lernen.items) == 7
    assert "fehlt000001" not in await collections.video_ids(f"playlist:{pl}")
    eintrag = next(p for p in await playlists_router.get_playlists() if p["id"] == pl)
    assert eintrag["pending_count"] == 3 and eintrag["video_count"] == 4

    eingereiht = []
    async def merken(ids, origin="auto"):
        eingereiht.extend(ids)
        return len(ids)
    monkeypatch.setattr(drip, "queue", merken)
    await playlists_router.update_playlist(pl, playlists_router.PlaylistUpdate(drip_enabled=True, drip_count=1))
    await test_db.execute("UPDATE playlists SET drip_count = 5, drip_next_run = datetime('now', '-1 minute') WHERE id = ?", (pl,))
    await drip.run_due()
    assert eingereiht == ["fehlt000001", "fehlt000002", "fehlt000003"]
    # Alles geladen: der nächste Lauf findet nichts und schaltet ab
    await test_db.execute("UPDATE videos SET status = 'ready' WHERE id LIKE 'fehlt%'")
    await test_db.execute("UPDATE playlists SET drip_next_run = datetime('now', '-1 minute') WHERE id = ?", (pl,))
    await drip.run_due()
    row = await test_db.fetch_one("SELECT drip_enabled, drip_completed_at FROM playlists WHERE id = ?", (pl,))
    assert row["drip_enabled"] == 0 and row["drip_completed_at"]


async def test_sammlung_nennt_musik_je_video(test_db, async_client_factory):
    """Menü der Videolisten (Wunsch 19.10.2026): "Als Musik" bzw. "Keine Musik" je Video;
    die Wahl gilt als Nutzerwahl und steht danach an der Sammlung."""
    from app.routers import videos
    await _video(test_db, "musik000001", "Lied", is_music=1)
    await _video(test_db, "vortrag0001", "Vortrag")
    for vid in ("musik000001", "vortrag0001"):
        await test_db.execute("INSERT INTO favorites (video_id, list_name) VALUES (?, 'Standard')", (vid,))
    music = {i.id: i.is_music for i in (await collections.load("favorites:Standard")).items}
    assert music == {"musik000001": True, "vortrag0001": False}
    async with await async_client_factory(videos.router) as client:
        listed = {v["id"]: v["is_music"] for v in (await client.get("/api/videos?per_page=10")).json()["videos"]}
        assert listed == {"musik000001": True, "vortrag0001": False}      # Kacheln der Bibliothek
        await client.post("/api/videos/music/batch", json={"video_ids": ["vortrag0001"], "is_music": True})
    assert all(i.is_music for i in (await collections.load("favorites:Standard")).items)
    assert await test_db.fetch_val("SELECT music_source FROM videos WHERE id = 'vortrag0001'") == "user"
