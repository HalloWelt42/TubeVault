"""
Shorts global ausschliessen (Einstellung shorts.exclude).

Kontrakt: Ist die Einstellung an, fehlen Shorts in Listen, Zählern, Suche und
Feed und werden nicht automatisch geladen. Gelöscht werden auf Wunsch nur
bestätigte Shorts - ungeprüfte bleiben.
"""
import pytest

from app.services import video_classifier as vc
from app.services.search import engine
from app.services.search.filters import SearchFilters
from app.services.counts_service import counts_service
from app.services.metadata_service import metadata_service
from app.services.rss_service import rss_service


@pytest.fixture
async def stock(test_db, tmp_path, monkeypatch):
    from app import config
    for name in ("VIDEOS_DIR", "THUMBNAILS_DIR", "SUBTITLES_DIR", "AUDIO_DIR", "METADATA_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCx', 'Kanal')")
    for vid, vtype, verified in (("normalvideo", "video", 1), ("bestaetigts", "short", 1),
                                 ("vermutetsho", "short", 0)):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, video_type, type_verified, channel_id) "
            "VALUES (?, ?, 'ready', ?, ?, 'UCx')", (vid, f"Clip {vid}", vtype, verified))
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, title, video_type, published) "
            "VALUES (?, 'UCx', ?, ?, '2026-01-01')", (vid, f"Clip {vid}", vtype))
    # Im Feed zählt nur, was noch nicht geladen ist
    for vid, vtype in (("neuesvideo1", "video"), ("neuershort", "short")):
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, title, video_type, published) "
            "VALUES (?, 'UCx', ?, ?, '2026-01-02')", (vid, f"Neu {vid}", vtype))


async def _ids():
    return {v["id"] for v in (await metadata_service.get_videos())["videos"]}


async def test_ohne_einstellung_alles_sichtbar(stock):
    assert await _ids() == {"normalvideo", "bestaetigts", "vermutetsho"}
    assert await counts_service.library_videos() == 3


async def test_ausgeschlossen_ueberall(stock, set_setting):
    await set_setting("shorts.exclude", "true")
    assert await _ids() == {"normalvideo"}
    assert await counts_service.library_videos() == 1
    assert [v.id for v in (await engine.section("videos", "Clip", SearchFilters())).items] == ["normalvideo"]
    feed = await rss_service.get_new_videos()
    assert [e["video_id"] for e in feed["entries"]] == ["neuesvideo1"]
    assert feed["tab_counts"]["active"] == 1


async def test_nur_bestaetigte_shorts_werden_geloescht(stock, test_db):
    overview = await vc.shorts_overview()
    assert overview["confirmed_shorts"] == 1 and overview["unverified"] >= 1
    assert await vc.delete_shorts() == 1
    remaining = {r["id"] for r in await test_db.fetch_all("SELECT id FROM videos")}
    assert remaining == {"normalvideo", "vermutetsho"}


async def test_kanal_freigabe_zeigt_seine_shorts(stock, set_setting, test_db):
    """Ausdrücklich freigegebener Kanal: seine Shorts erscheinen trotz Ausschluss,
    der Typ bleibt Short; andere Kanäle bleiben ohne Shorts."""
    await set_setting("shorts.exclude", "true")
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCy', 'Anderer')")
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title, video_type, published) "
        "VALUES ('fremdershort', 'UCy', 'Fremd', 'short', '2026-01-03')")
    assert await vc.hidden_short_count("UCx") == 3

    await vc.set_channel_short_allowed("UCx", True)
    assert await vc.hidden_short_count("UCx") == 0
    assert await _ids() == {"normalvideo", "bestaetigts", "vermutetsho"}
    feed = {e["video_id"] for e in (await rss_service.get_new_videos())["entries"]}
    assert feed == {"neuesvideo1", "neuershort"}
    assert await test_db.fetch_val("SELECT video_type FROM videos WHERE id = 'bestaetigts'") == "short"

    await vc.set_channel_short_allowed("UCx", False)
    assert await _ids() == {"normalvideo"}


async def test_kanalseite_zaehlt_wie_die_liste(stock, set_setting):
    from app.routers.subscriptions import _get_channel_videos_impl
    await set_setting("shorts.exclude", "true")
    page = await _get_channel_videos_impl("UCx", "all", "all", "newest", 1, 50, False)
    assert page["total"] == len(page["videos"]) == page["source_counts"]["all"] == 2
    await vc.set_channel_short_allowed("UCx", True)
    page = await _get_channel_videos_impl("UCx", "all", "all", "newest", 1, 50, False)
    assert page["source_counts"]["all"] == 5
