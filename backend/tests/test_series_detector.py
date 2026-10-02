"""
Serien erkennen (app/services/series_detector.py) - mit echten Titelformen.
"""
import pytest

from app.services import series_detector as sd


def _videos(channel, titles):
    return [{"id": f"{channel}{n:03d}", "title": t, "channel_id": channel, "channel_name": f"Kanal {channel}",
             "upload_date": f"2026-01-{n + 1:02d}"} for n, t in enumerate(titles)]


def _by_name(series):
    return {s.name: s for s in series}


def test_kennzeichen_in_titeln():
    f = sd.find_matches
    assert [(m.kind, m.number, m.before) for m in f("C++ Tutorial #8: Palindromtest")] == [("raute", 8, "C++ Tutorial")]
    assert [(m.kind, m.number) for m in f("Alpha Centauri - Was ist der Sonnenwind - Folge 75")] == [("wort", 75)]
    assert [(m.kind, m.season, m.number) for m in f("S02E22: Hyperspace (Part 2) | Starhunter")][0] == ("staffel", 2, 22)
    both = f("Digitalisierung verstehen lernen Teil 10: die totale Automatisierung | mmM#167")
    assert {(m.kind, m.number) for m in both} == {("wort", 10), ("kuerzel", 167)}
    assert f("Das Geburtstagsparadoxon #mathe #uni #schule") == [], "Schlagworte sind keine Folgen"
    assert [(m.kind, m.number) for m in f("Blender 3D-Charakterworkshop Teil 2 | #02 - Vorbereitung")] == [("wort", 2)]
    assert f("Ubuntu: Der eigene DVD Media Server (Teil 2 von 3)")[0].before == "Ubuntu: Der eigene DVD Media Server"


def test_mehrere_serien_eines_kanals_bleiben_getrennt():
    videos = _videos("A", [
        "C++ Tutorial #1: Hallo Welt", "C++ Tutorial #2: Variablen", "C++ Tutorial #3: Schleifen",
        "Python Tutorial #1: Start", "Python Tutorial #2: Listen", "Python Tutorial #3: Dateien",
        "Ein Einzelvideo ohne Nummer",
    ])
    series = _by_name(sd.detect(videos))
    assert set(series) == {"C++ Tutorial", "Python Tutorial"}
    assert [e.number for e in series["C++ Tutorial"].episodes] == [1, 2, 3]


def test_gleicher_serienname_in_zwei_kanaelen():
    videos = _videos("A", ["Tutorial #1", "Tutorial #2", "Tutorial #3"]) \
        + _videos("B", ["Tutorial #1", "Tutorial #2", "Tutorial #3"])
    assert len(sd.detect(videos)) == 2


def test_thema_vor_der_folgennummer():
    videos = _videos("A", [
        "Alpha Centauri - Was ist der Sonnenwind - Folge 75",
        "Alpha Centauri - Gibt es Dunkle Materie - Folge 76",
        "Alpha Centauri - Was sind Quasare - Folge 78",
    ])
    series = sd.detect(videos)
    assert [(s.name, s.first, s.last, s.missing) for s in series] == [("Alpha Centauri", 75, 78, [77])]


def test_mehrteiler_schlaegt_ersten_abschnitt():
    videos = _videos("A", [
        "Ubuntu: Der eigene DVD Media Server (Teil 1 von 3)",
        "Ubuntu: Der eigene DVD Media Server (Teil 2 von 3)",
        "Ubuntu: Der eigene DVD Media Server (Teil 3 von 3)",
        "Ubuntu: Backup einrichten (Teil 1 von 2)",
        "Ubuntu: Backup einrichten (Teil 2 von 2)",
    ])
    series = _by_name(sd.detect(videos))
    assert list(series) == ["Ubuntu: Der eigene DVD Media Server"], \
        "der genauere Name gewinnt; der Zweiteiler ist zu kurz und wird nicht unter 'Ubuntu' vermischt"


def test_kuerzel_serien_und_doppelte_zugehoerigkeit():
    videos = _videos("A", [
        "Digitalisierung verstehen lernen Teil 9: Anfang | mmM#166",
        "Digitalisierung verstehen lernen Teil 10: die totale Automatisierung | mmM#167",
        "Digitalisierung verstehen lernen Teil 11: Ende | mmM#168",
        "deutsche Kultur ist ein Oxymoron | mmM#252",
        "Kamingespräch: mehr Fragen | gmm#94", "Gast mit Meinung | gmM#89", "Noch ein Gast | gmm#95",
    ])
    series = _by_name(sd.detect(videos))
    assert set(series) == {"mmM", "gmm", "Digitalisierung verstehen lernen"}
    assert [e.number for e in series["mmM"].episodes] == [166, 167, 168, 252]
    assert len(series["Digitalisierung verstehen lernen"].episodes) == 3


def test_reihenfolge_nach_staffel_und_folge():
    videos = _videos("A", ["S02E01: B | Starhunter", "S01E02: A2 | Starhunter", "S01E01: A1 | Starhunter",
                           "S02E02: B2 | Starhunter", "S01E03: A3 | Starhunter", "S02E03: B3 | Starhunter"])
    series = sd.detect(videos)
    assert sorted(s.name for s in series) == ["Kanal A Staffel 1", "Kanal A Staffel 2"]


def test_zu_wenige_folgen_sind_keine_serie():
    assert sd.detect(_videos("A", ["Reisen #1", "Reisen #2"])) == []
    assert len(sd.detect(_videos("A", ["Reisen #1", "Reisen #2"]), min_episodes=2)) == 1


async def _insert(test_db, videos):
    for v in videos:
        await test_db.execute(
            "INSERT INTO videos (id, title, channel_id, channel_name, status, upload_date) VALUES (?, ?, ?, ?, 'ready', ?)",
            (v["id"], v["title"], v["channel_id"], v["channel_name"], v["upload_date"]))


async def test_playlist_anlegen_und_auffrischen(test_db):
    await _insert(test_db, _videos("A", ["Kurs #3: C", "Kurs #1: A", "Kurs #2: B"]))
    found = await sd.proposals()
    assert found[0].playlist_id is None

    created = await sd.create_playlist(found[0].key)
    assert created["name"] == "Kurs (Kanal A)" and created["video_count"] == 3
    order = [r["video_id"] for r in await test_db.fetch_all(
        "SELECT video_id FROM playlist_videos WHERE playlist_id = ? ORDER BY position", (created["playlist_id"],))]
    assert order == ["A001", "A002", "A000"], "Reihenfolge nach Folgennummer"

    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, channel_name, status) VALUES ('A099', 'Kurs #4: D', 'A', 'Kanal A', 'ready')")
    again = await sd.create_playlist(found[0].key)
    assert again["playlist_id"] == created["playlist_id"] and again["video_count"] == 4
    assert (await sd.proposals())[0].playlist_id == created["playlist_id"]
    assert await test_db.fetch_val("SELECT COUNT(*) FROM playlists") == 1


async def test_playlist_aus_trefferliste(test_db):
    await _insert(test_db, _videos("A", ["Eins", "Zwei", "Drei"]))
    pid = await sd.save_playlist("Meine Treffer", ["A002", "A000", "A002"])
    rows = await test_db.fetch_all("SELECT video_id FROM playlist_videos WHERE playlist_id = ? ORDER BY position", (pid,))
    assert [r["video_id"] for r in rows] == ["A002", "A000"]
