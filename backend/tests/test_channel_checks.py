"""
Kanal-Bereich: Prüfplanung, Auto-Download, Scan und Job-Absicherung.

Hält die Fehler fest, die den Bereich im Alltag unzuverlässig machten:
  - ruhige Kanäle wurden nur noch alle 7 Tage geprüft
  - eine Netzstörung bestrafte jeden einzelnen Kanal
  - jede Prüfung fragte auch für längst bekannte Videos den Typ ab
  - Auto-Download verlor Videos, wenn das Tageslimit erreicht war
  - ein gestörter oder abgebrochener Scan galt als erfolgreich
  - abgestürzte Läufe blieben "aktiv" und sperrten alle folgenden
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.services import channel_reference, channel_scanner, loadable, video_classifier
from app.services.job_service import job_service
from app.services.rate_limiter import rate_limiter
from app.services.rss_service import ChannelNotFound, rss_service

CH = ["UC" + f"{n:022d}" for n in range(6)]


def item(video_id, **kw):
    return SimpleNamespace(video_id=video_id, title=kw.get("title", video_id),
                           thumbnail_url=None, publish_date=kw.get("date"),
                           length=kw.get("length", 600), views=kw.get("views", 0))


@pytest.fixture
async def feeds(test_db, monkeypatch):
    """Kanäle ohne Netz: je Kanal eine vorbereitete Liste oder ein Fehler."""
    monkeypatch.setattr(rate_limiter, "disabled", True)
    for attr, value in (("_polling", False), ("_disturbed_until", None),
                        ("_disturbance_count", 0), ("_disturbance_reason", "")):
        monkeypatch.setattr(rss_service, attr, value)
    monkeypatch.setattr(job_service, "_semaphore", asyncio.Semaphore(1))
    monkeypatch.setattr(job_service, "_sem_held_by", set())
    monkeypatch.setattr(job_service, "_cancelled", set())
    await test_db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('rss.enabled', 'true')")

    answers: dict[str, object] = {}

    async def fetch_latest(channel_id):
        answer = answers.get(channel_id, [])
        if isinstance(answer, Exception):
            raise answer
        return "Name " + channel_id[-2:], answer

    async def no_typed(channel_id):
        return set(), set()

    monkeypatch.setattr(rss_service, "_fetch_latest", fetch_latest)
    monkeypatch.setattr(rss_service, "_fetch_typed_video_ids", no_typed)
    return answers


async def subscribe(db, channel_id, **columns):
    columns = {"channel_name": "Kanal", "check_interval": 1800, "enabled": 1, **columns}
    names = ", ".join(columns)
    marks = ", ".join("?" * len(columns))
    await db.execute(
        f"INSERT INTO subscriptions (channel_id, {names}) VALUES (?, {marks})",
        (channel_id, *columns.values()))


async def sub_row(db, channel_id):
    return dict(await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)))


# ─── Prüfplanung ──────────────────────────────────────────

async def test_intervall_waechst_nur_bis_zur_obergrenze(feeds, test_db, set_setting):
    await set_setting("rss.max_interval", 7200)
    await subscribe(test_db, CH[0], check_interval=3600)
    await subscribe(test_db, CH[1], check_interval=604800)   # alter 7-Tage-Wert

    result = await rss_service.tick()

    assert result["status"] == "completed" and result["checked"] == 2
    assert (await sub_row(test_db, CH[0]))["check_interval"] == 7200
    # der alte 7-Tage-Wert wird auf die Obergrenze gekappt
    assert (await sub_row(test_db, CH[1]))["check_interval"] == 7200


async def test_neue_videos_setzen_auf_basisintervall(feeds, test_db):
    await subscribe(test_db, CH[0], check_interval=43200)
    feeds[CH[0]] = [item("neu00000001")]

    result = await rss_service.tick()

    assert result["new_videos"] == 1
    assert (await sub_row(test_db, CH[0]))["check_interval"] == 1800


async def test_fehler_eines_kanals_trifft_nur_diesen(feeds, test_db):
    await subscribe(test_db, CH[0])
    await subscribe(test_db, CH[1])
    feeds[CH[0]] = RuntimeError("HTTP Error 404: Not Found")

    result = await rss_service.tick()

    assert result["status"] == "completed" and result["errors"] == 1
    broken, fine = await sub_row(test_db, CH[0]), await sub_row(test_db, CH[1])
    assert broken["error_count"] == 1 and broken["last_checked"]
    assert fine["error_count"] == 0 and fine["last_checked"]


async def test_stoerung_der_quelle_bestraft_keinen_kanal(feeds, test_db):
    for channel_id in CH[:4]:
        await subscribe(test_db, channel_id)
        feeds[channel_id] = RuntimeError("Sign in to confirm you're not a bot")

    result = await rss_service.tick()

    assert result["status"] == "disturbed"
    for channel_id in CH[:4]:
        row = await sub_row(test_db, channel_id)
        assert row["error_count"] == 0 and row["check_interval"] == 1800
        assert row["last_checked"] is None        # bleibt fällig
    # Der nächste Anstoß pausiert sichtbar, statt weiter anzufragen
    again = await rss_service.tick()
    assert again["status"] == "skipped" and "gestört" in again["message"]
    assert rss_service._last_tick["status"] == "skipped"


async def test_mehrere_fehlschlaege_in_folge_gelten_als_stoerung(feeds, test_db):
    for channel_id in CH[:5]:
        await subscribe(test_db, channel_id)
        feeds[channel_id] = RuntimeError("irgendein unbekannter Fehler")

    result = await rss_service.tick()

    assert result["status"] == "disturbed" and result["checked"] == 0
    assert all([(await sub_row(test_db, c))["error_count"] == 0 for c in CH[:5]])


async def test_anstoss_waehrend_scan_setzt_sichtbar_aus(feeds, test_db):
    await subscribe(test_db, CH[0])
    job_service._sem_held_by.add(99)

    result = await rss_service.tick()

    assert result["status"] == "skipped"
    assert (await sub_row(test_db, CH[0]))["last_checked"] is None


async def test_bekannte_videos_werden_nicht_erneut_eingeordnet(feeds, test_db, monkeypatch):
    await subscribe(test_db, CH[0])
    feeds[CH[0]] = [item("kurz0000001", length=30), item("kurz0000002", length=30)]
    asked = []

    async def classify(video_id, duration=None, **kw):
        asked.append(video_id)
        return SimpleNamespace(video_type="video", verified=True)
    monkeypatch.setattr(video_classifier, "classify", classify)

    sub = await sub_row(test_db, CH[0])
    assert await rss_service._poll_single_feed(sub) == 2
    assert await rss_service._poll_single_feed(sub) == 0
    assert asked == ["kurz0000001", "kurz0000002"]      # nur beim ersten Mal


async def test_zaehler_des_abos_folgen_der_datenbank(feeds, test_db):
    await subscribe(test_db, CH[0])
    feeds[CH[0]] = [item("vid00000001"), item("vid00000002")]
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, video_type) VALUES ('sho00000001', ?, 'short')",
        (CH[0],))

    await rss_service._poll_single_feed(await sub_row(test_db, CH[0]))

    row = await sub_row(test_db, CH[0])
    assert (row["video_count"], row["shorts_count"], row["live_count"]) == (2, 1, 0)


async def test_einzelpruefung_von_hand_verlaengert_das_intervall_nicht(feeds, test_db):
    await subscribe(test_db, CH[0], check_interval=3600)
    sub_id = (await sub_row(test_db, CH[0]))["id"]

    result = await rss_service.check_channel_now(sub_id)

    assert result["new_videos"] == 0
    assert (await sub_row(test_db, CH[0]))["check_interval"] == 3600


# ─── Auto-Download ────────────────────────────────────────

async def test_auto_download_holt_nach_dem_tageslimit_nach(feeds, test_db, set_setting):
    await set_setting("rss.auto_dl_daily_limit", 2)
    await subscribe(test_db, CH[0], auto_download=1)
    feeds[CH[0]] = [item(f"auto000000{n}") for n in range(5)]

    await rss_service.tick()

    queued = await test_db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type = 'download'")
    pending = await test_db.fetch_val("SELECT COUNT(*) FROM rss_entries WHERE auto_pending = 1")
    assert (queued, pending) == (2, 3)

    # Neuer Tag: Zähler ist abgelaufen, die Vorgemerkten rücken nach
    await test_db.execute("DELETE FROM settings WHERE key = 'rss.auto_dl_counter'")
    assert await rss_service.queue_pending_auto_downloads() == 2
    assert await test_db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE auto_pending = 1") == 1


async def test_vormerkung_verfaellt_wenn_auto_download_abgeschaltet(feeds, test_db, set_setting):
    await set_setting("rss.auto_dl_daily_limit", 1)
    await subscribe(test_db, CH[0], auto_download=1)
    feeds[CH[0]] = [item("auto0000001"), item("auto0000002")]
    await rss_service.tick()
    await test_db.execute("UPDATE subscriptions SET auto_download = 0")
    await test_db.execute("DELETE FROM settings WHERE key = 'rss.auto_dl_counter'")

    assert await rss_service.queue_pending_auto_downloads() == 0
    assert await test_db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE auto_pending = 1") == 0


async def test_ladbar_schliesst_ignorierte_geparkte_und_livestreams_aus(feeds, test_db):
    rows = [("ok000000001", "video"), ("ign00000001", "video"),
            ("park0000001", "video"), ("live0000001", "live")]
    for video_id, video_type in rows:
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, video_type) VALUES (?, ?, ?)",
            (video_id, CH[0], video_type))
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id, reason) VALUES ('ign00000001', ?, 'manual')",
        (CH[0],))
    await test_db.execute(
        """INSERT INTO jobs (type, title, status, metadata)
           VALUES ('download', 'x', 'parked', '{"video_id": "park0000001"}')""")

    assert await loadable.count(CH[0]) == 1
    assert await loadable.is_loadable("ok000000001")
    assert not await loadable.is_loadable("park0000001")


# ─── Hinzufügen ───────────────────────────────────────────

async def test_unbekannter_kanal_wird_kein_abo(feeds, test_db, monkeypatch):
    from app.utils import pytube_client

    def broken(url, **kw):
        raise RuntimeError("This channel does not exist")
    monkeypatch.setattr(pytube_client, "make_channel", broken)

    with pytest.raises(ChannelNotFound):
        await rss_service.add_subscription(CH[0])
    assert await test_db.fetch_val("SELECT COUNT(*) FROM subscriptions") == 0


async def test_verweis_aufloesen(monkeypatch):
    assert await channel_reference.resolve(f"  {CH[0]} ") == CH[0]
    assert await channel_reference.resolve(
        f"https://www.youtube.com/channel/{CH[1]}/videos?view=0") == CH[1]

    asked = []

    def lookup(text):
        asked.append(text)
        return CH[2]
    monkeypatch.setattr(channel_reference, "_lookup", lookup)
    assert await channel_reference.resolve("@werkbank") == CH[2]
    assert asked == ["@werkbank"]

    monkeypatch.setattr(channel_reference, "_lookup", lambda text: "")
    with pytest.raises(channel_reference.UnresolvableChannel):
        await channel_reference.resolve("irgendein text")
    with pytest.raises(channel_reference.UnresolvableChannel):
        await channel_reference.resolve("")


async def test_alle_entsperren_schaltet_abgeschaltete_nicht_ein(feeds, test_db):
    from app.routers.subscriptions import reset_all_errors
    await subscribe(test_db, CH[0], enabled=0)
    await subscribe(test_db, CH[1], error_count=4, check_interval=86400, last_error="x")

    result = await reset_all_errors()

    assert result["reset"] == 1
    assert (await sub_row(test_db, CH[0]))["enabled"] == 0
    fixed = await sub_row(test_db, CH[1])
    assert (fixed["error_count"], fixed["check_interval"], fixed["last_error"]) == (0, 1800, None)


# ─── Kanal-Scan ───────────────────────────────────────────

class FakeChannel:
    """Kanal mit drei Listen; eine Liste kann mitten im Lesen scheitern."""
    channel_name = "Werkbank"
    description = "Beschreibung"
    subscriber_count = 4321
    banner_url = ""
    tags = ["holz"]
    videos_url, shorts_url, live_url = "videos", "shorts", "live"

    def __init__(self, lists):
        self.lists = lists
        self.html_url = None

    def url_generator(self):
        for entry in self.lists[self.html_url]:
            if isinstance(entry, Exception):
                raise entry
            yield entry


@pytest.fixture
async def scan(feeds, test_db, monkeypatch):
    from app.utils import pytube_client
    lists = {"videos": [], "shorts": [], "live": []}
    monkeypatch.setattr(pytube_client, "make_channel", lambda url, **kw: FakeChannel(lists))
    await subscribe(test_db, CH[0])
    return lists


async def test_scan_speichert_und_gilt_als_gescannt(scan, test_db):
    scan["videos"] = [item(f"vid0000000{n}", date="20260115") for n in range(3)]
    scan["shorts"] = [item("sho00000001")]

    result = await channel_scanner.fetch_all_channel_videos(CH[0])

    row = await sub_row(test_db, CH[0])
    assert result["new"] == 4 and not result["scan_errors"]
    assert row["last_scanned"] and row["subscriber_count"] == 4321
    assert (row["video_count"], row["shorts_count"]) == (3, 1)
    assert await test_db.fetch_val(
        "SELECT published FROM rss_entries WHERE video_id = 'vid00000000'"
    ) == "2026-01-15T00:00:00+00:00"
    job = await test_db.fetch_one("SELECT status FROM jobs WHERE type = 'channel_scan'")
    assert job["status"] == "done"


async def test_gestoerter_scan_gilt_nicht_als_gescannt(scan, test_db):
    scan["videos"] = [item("vid00000001"), RuntimeError("HTTP Error 429")]

    result = await channel_scanner.fetch_all_channel_videos(CH[0])

    row = await sub_row(test_db, CH[0])
    job = await test_db.fetch_one(
        "SELECT status, error_message FROM jobs WHERE type = 'channel_scan'")
    assert result["scan_errors"] == {"video": "HTTP Error 429"}
    assert row["last_scanned"] is None
    assert job["status"] == "error" and "unvollständig" in job["error_message"]
    # Was gefunden wurde, bleibt erhalten
    assert await test_db.fetch_val("SELECT COUNT(*) FROM rss_entries") == 1
    assert not job_service.is_exclusive_running()


async def test_scan_bricht_ab_und_gibt_den_platz_frei(scan, test_db):
    job = await job_service.create(job_type="channel_scan", title="Scan")

    class Endless(list):
        def __iter__(self):
            n = 0
            while True:
                n += 1
                if n == 5:
                    job_service._cancelled.add(job["id"])
                import time
                time.sleep(0.25)
                yield item(f"vid{n:08d}")
    scan["videos"] = Endless()

    result = await asyncio.wait_for(
        channel_scanner.fetch_all_channel_videos(CH[0], job_id=job["id"]), timeout=20)

    assert result["cancelled"] is True
    assert (await sub_row(test_db, CH[0]))["last_scanned"] is None
    assert not job_service.is_exclusive_running()


# ─── Job-Absicherung ──────────────────────────────────────

async def test_abgestuerzter_lauf_gibt_den_platz_frei(feeds, test_db):
    job = await job_service.create(job_type="import", title="Import")
    await job_service.start(job["id"])

    with pytest.raises(RuntimeError):
        async with job_service.guard(job["id"]):
            raise RuntimeError("kaputt")

    assert (await job_service.get(job["id"]))["status"] == "error"
    assert not job_service.is_exclusive_running()


async def test_lauf_wartet_nicht_auf_downloads(feeds, test_db):
    await test_db.execute(
        "INSERT INTO jobs (type, title, status) VALUES ('download', 'läuft', 'active')")
    job = await job_service.create(job_type="channel_scan", title="Scan")

    started = await asyncio.wait_for(job_service.start(job["id"]), timeout=2)

    assert started["status"] == "active"


async def test_abbruch_waehrend_des_wartens_startet_nicht(feeds, test_db):
    first = await job_service.create(job_type="channel_scan", title="A")
    second = await job_service.create(job_type="channel_scan", title="B")
    await job_service.start(first["id"])
    waiting = asyncio.create_task(job_service.start(second["id"]))
    await asyncio.sleep(0.05)

    await job_service.cancel(second["id"])
    await job_service.complete(first["id"])
    await asyncio.wait_for(waiting, timeout=2)

    assert (await job_service.get(second["id"]))["status"] == "cancelled"
    assert not job_service.is_exclusive_running()


# ─── Abo-Liste ────────────────────────────────────────────

async def test_abo_liste_zaehlt_je_kanal(feeds, test_db):
    await subscribe(test_db, CH[0], channel_name="beta")
    await subscribe(test_db, CH[1], channel_name="Alpha")
    for n in range(3):
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, status) VALUES (?, ?, 'new')",
            (f"vid0000000{n}", CH[0]))
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, status) VALUES ('vid00000000', 't', ?, 'ready')""",
        (CH[0],))
    await test_db.execute(
        """INSERT INTO jobs (type, title, status, metadata)
           VALUES ('download', 'x', 'parked', '{"video_id": "vid00000001"}')""")

    result = await rss_service.get_subscriptions(page=1, per_page=50)

    names = [row["channel_name"] for row in result["subscriptions"]]
    assert names == ["Alpha", "beta"]          # Groß-/Kleinschreibung trennt nicht
    beta = result["subscriptions"][1]
    assert (beta["rss_count"], beta["new_videos"], beta["downloaded_count"],
            beta["problem_count"]) == (3, 2, 1, 1)      # das geladene Video ist nicht mehr neu
    alpha = result["subscriptions"][0]
    assert (alpha["rss_count"], alpha["downloaded_count"], alpha["problem_count"]) == (0, 0, 0)


# ─── Feed ─────────────────────────────────────────────────

async def test_geladene_videos_zaehlen_im_feed_nicht_als_neu(feeds, test_db):
    from app.services.counts_service import counts_service
    await subscribe(test_db, CH[0])
    for video_id in ("neu00000001", "neu00000002", "geladen0001"):
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, status) VALUES (?, ?, 'new')",
            (video_id, CH[0]))
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status) VALUES ('geladen0001', 't', ?, 'ready')",
        (CH[0],))

    feed = await rss_service.get_new_videos(feed_tab="active")
    assert sorted(entry["video_id"] for entry in feed["entries"]) == ["neu00000001", "neu00000002"]
    assert feed["total"] == 2 and feed["tab_counts"]["active"] == 2
    assert await counts_service.feed_new() == 2
    assert (await rss_service.get_stats())["new_videos"] == 2
    listed = (await rss_service.get_subscriptions())["subscriptions"][0]
    assert (listed["rss_count"], listed["new_videos"]) == (3, 2)
