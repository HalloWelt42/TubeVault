"""
Tests für ChannelAdapter – pytubefix-kompatible API für den Channel-Scanner.

Regression-Schutz: channel_scanner.py ruft ch.html_url = ch.videos_url
(bzw. .shorts_url/.live_url) und iteriert dann ch.url_generator().
Fehlt eine dieser Methoden, findet der Scan 0 Videos (Bug v2.5.0).

Netzwerk-freie Tests: nur die URL-Logik + API-Vorhandensein.
"""
import pytest

from app.utils.ytdlp_adapter import ChannelAdapter


def test_tab_urls_from_handle():
    ch = ChannelAdapter("https://www.youtube.com/@3blue1brown")
    assert ch.videos_url == "https://www.youtube.com/@3blue1brown/videos"
    assert ch.shorts_url == "https://www.youtube.com/@3blue1brown/shorts"
    assert ch.live_url == "https://www.youtube.com/@3blue1brown/streams"


def test_tab_urls_strip_existing_suffix():
    """Egal ob URL schon /videos, /shorts etc. hat – Basis wird sauber."""
    for suffix in ("/videos", "/shorts", "/streams", "/about", "/featured"):
        ch = ChannelAdapter(f"https://www.youtube.com/channel/UCabc{suffix}")
        assert ch.videos_url == "https://www.youtube.com/channel/UCabc/videos"
        assert ch.shorts_url == "https://www.youtube.com/channel/UCabc/shorts"
        assert ch.live_url == "https://www.youtube.com/channel/UCabc/streams"


def test_tab_urls_trailing_slash():
    ch = ChannelAdapter("https://www.youtube.com/channel/UCxyz/")
    assert ch.videos_url == "https://www.youtube.com/channel/UCxyz/videos"


def test_html_url_settable_and_default_none():
    """channel_scanner setzt ch.html_url – muss settable sein, default None."""
    ch = ChannelAdapter("https://www.youtube.com/@test")
    assert ch.html_url is None
    ch.html_url = ch.shorts_url
    assert ch.html_url == "https://www.youtube.com/@test/shorts"


def test_url_generator_exists_and_is_generator():
    """url_generator muss existieren (Bug: ChannelAdapter hatte sie nicht)."""
    ch = ChannelAdapter("https://www.youtube.com/@test")
    assert hasattr(ch, "url_generator")
    gen = ch.url_generator.__call__
    import inspect
    assert inspect.isgeneratorfunction(ChannelAdapter.url_generator)


class FakeListing:
    """Ersetzt yt_dlp.YoutubeDL für Listen-Abrufe: liefert vorbereitete
    Antworten und merkt sich, womit und wie oft gefragt wurde."""

    def __init__(self, monkeypatch, info=None, error=None):
        from app.utils import ytdlp_adapter as mod
        self.info, self.error = info, error
        self.calls, self.opts, self.consumed = [], None, 0
        listing = self

        class FakeYDL:
            def __init__(self, opts):
                listing.opts = opts

            def extract_info(self, url, download=False, process=True):
                listing.calls.append((url, process))
                if listing.error:
                    raise listing.error
                info = dict(listing.info)
                info["entries"] = listing._entries(info.get("entries") or [])
                return info

        monkeypatch.setattr(mod.yt_dlp, "YoutubeDL", FakeYDL)
        monkeypatch.setattr(mod, "_LISTING_RETRY_PAUSE_S", 0)

    def _entries(self, entries):
        for entry in entries:
            self.consumed += 1
            yield entry


def test_url_generator_missing_tab_is_empty(monkeypatch):
    """Hat der Kanal den Reiter nicht (z.B. keine Shorts) → leere Liste."""
    FakeListing(monkeypatch, error=RuntimeError("This channel does not have a Shorts tab"))
    ch = ChannelAdapter("https://www.youtube.com/@test")
    ch.html_url = ch.shorts_url
    assert list(ch.url_generator()) == []


def test_url_generator_real_failure_is_not_an_empty_channel(monkeypatch):
    """Eine Störung darf nicht wie ein leerer Kanal aussehen - sonst gilt
    ein gescheiterter Scan als erfolgreich."""
    listing = FakeListing(monkeypatch, error=RuntimeError("HTTP Error 429: Too Many Requests"))
    ch = ChannelAdapter("https://www.youtube.com/@test")
    with pytest.raises(RuntimeError, match="429"):
        list(ch.url_generator())
    assert len(listing.calls) == 2   # ein Wiederholungsversuch


def test_url_generator_yields_channel_video_items(monkeypatch):
    """Flat-Entries werden zu ChannelVideoItem mit den Feldern, die der
    Scanner liest (video_id, title, length, views, thumbnail_url, publish_date)."""
    FakeListing(monkeypatch, info={
        "channel": "TestChan",
        "channel_id": "UCtest",
        "entries": [
            {"id": "vid1aaaaaaa", "title": "Erstes Video", "duration": 120,
             "view_count": 999, "upload_date": "20260101"},
            {"id": "vid2bbbbbbb", "title": "Zweites", "duration": 60},
            None,  # muss übersprungen werden
        ],
    })
    ch = ChannelAdapter("https://www.youtube.com/@test")
    ch.html_url = ch.videos_url
    items = list(ch.url_generator())
    assert len(items) == 2
    assert items[0].video_id == "vid1aaaaaaa"
    assert items[0].title == "Erstes Video"
    assert items[0].length == 120
    assert items[0].views == 999
    assert items[0].channel_id == "UCtest"
    assert items[1].video_id == "vid2bbbbbbb"


def test_listing_uses_web_client_and_desktop_ua(monkeypatch):
    """Kanal-Reiter müssen mit festem web-Client + Desktop-UA laufen –
    sonst 'Unable to recognize tab page'. Gelesen wird träge (process=False)."""
    listing = FakeListing(monkeypatch, info={"channel": "C", "channel_id": "UCx", "entries": []})
    ch = ChannelAdapter("https://www.youtube.com/@x")
    list(ch.url_generator())
    assert listing.opts["extractor_args"]["youtube"]["player_client"] == ["web"]
    ua = listing.opts["http_headers"]["User-Agent"]
    assert "Mobile" not in ua and "iPhone" not in ua and "Android" not in ua
    assert listing.opts["extract_flat"] == "in_playlist"
    assert listing.calls == [("https://www.youtube.com/@x/videos", False)]


def test_channel_head_does_not_read_the_list(monkeypatch):
    """Name, Bild, Abonnenten: ein Abruf, kein einziger Listeneintrag."""
    listing = FakeListing(monkeypatch, info={
        "channel": "Werkbank", "channel_id": "UCx", "channel_follower_count": 1234,
        "tags": ["löten", "holz"], "description": "Text",
        "uploader_url": "https://www.youtube.com/@werkbank",
        "thumbnails": [
            {"url": "klein", "width": 88, "height": 88},
            {"url": "avatar", "id": "avatar_uncropped"},
            {"url": "banner-schmal", "width": 1060, "height": 175},
            {"url": "banner-breit", "width": 2560, "height": 424},
            {"url": "banner-roh", "id": "banner_uncropped"},
        ],
        "entries": [{"id": f"v{n:010d}"} for n in range(500)],
    })
    ch = ChannelAdapter("https://www.youtube.com/channel/UCx")
    assert ch.channel_name == "Werkbank"
    assert ch.channel_id == "UCx"
    assert ch.subscriber_count == 1234
    assert ch.tags == ["löten", "holz"]
    assert ch.thumbnail_url == "avatar"
    assert ch.banner_url == "banner-breit"
    assert ch.vanity_url == "https://www.youtube.com/@werkbank"
    assert len(listing.calls) == 1
    assert listing.consumed == 0


def test_videos_stop_at_max_videos(monkeypatch):
    """Die Prüfung liest nur die neuesten Einträge - der Rest wird nie geholt."""
    listing = FakeListing(monkeypatch, info={
        "channel": "C", "channel_id": "UCx",
        "entries": [{"id": f"v{n:010d}"} for n in range(500)],
    })
    ch = ChannelAdapter("https://www.youtube.com/channel/UCx", max_videos=15)
    assert len(list(ch.videos)) == 15
    assert listing.consumed <= 16
    assert ch.channel_name == "C"
    assert len(listing.calls) == 1   # Name stammt aus dem Kopf der Liste


def test_desktop_ua_pool_has_no_mobile():
    """Desktop-Pool darf keinen Mobile/iPhone/Android-UA enthalten."""
    from app.utils.ytdlp_adapter import _DESKTOP_UA_POOL
    assert len(_DESKTOP_UA_POOL) >= 3
    for ua in _DESKTOP_UA_POOL:
        assert "Mobile" not in ua
        assert "iPhone" not in ua
        assert "Android" not in ua


def test_force_clients_sets_web_and_desktop_ua(monkeypatch):
    """Mit force_clients=['web'] + desktop_ua_only landet im finalen
    yt-dlp-opts genau dieser Client und ein Desktop-UA (kein Mobile)."""
    from app.utils import ytdlp_adapter as mod
    captured = {}

    class FakeYDL:
        def __init__(self, opts): captured["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {"entries": []}

    monkeypatch.setattr(mod.yt_dlp, "YoutubeDL", FakeYDL)
    mod._ydl_extract("https://youtube.com/@x/videos",
                     force_clients=["web"], desktop_ua_only=True)
    o = captured["opts"]
    assert o["extractor_args"]["youtube"]["player_client"] == ["web"]
    ua = o["http_headers"]["User-Agent"]
    assert "Mobile" not in ua and "iPhone" not in ua and "Android" not in ua
    # POT-Provider muss trotz force_clients erhalten bleiben
    assert o["extractor_args"]["youtubepot-bgutilhttp"]["base_url"]


def test_url_generator_resolves_nested_playlist(monkeypatch):
    """Manche Channel-Tabs liefern verschachtelte Sub-Playlists –
    die müssen aufgelöst werden, sonst fehlen Videos."""
    FakeListing(monkeypatch, info={
        "channel": "C", "channel_id": "UCx",
        "entries": [
            {"_type": "playlist", "entries": [
                {"id": "nested1aaaa", "title": "N1"},
                {"id": "nested2bbbb", "title": "N2"},
            ]},
            {"id": "flat3cccccc", "title": "F3"},
        ],
    })
    ch = ChannelAdapter("https://www.youtube.com/@x")
    ids = [v.video_id for v in ch.url_generator()]
    assert ids == ["nested1aaaa", "nested2bbbb", "flat3cccccc"]


def test_item_date_falls_back_to_approximate_timestamp():
    """Die Liste kennt kein upload_date; das ungefähre Datum der Quelle
    (Zeitstempel) wird genauso geschrieben."""
    from app.utils.ytdlp_adapter import ChannelVideoItem
    assert ChannelVideoItem({"id": "a", "timestamp": 1790121600}).publish_date == "20260923"
    assert ChannelVideoItem({"id": "a", "upload_date": "20250101",
                             "timestamp": 1790121600}).publish_date == "20250101"
    assert ChannelVideoItem({"id": "a"}).publish_date is None
