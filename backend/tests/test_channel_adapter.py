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


def test_url_generator_handles_extract_failure_gracefully(monkeypatch):
    """Wenn yt-dlp scheitert (z.B. kein Shorts-Tab) → leerer Generator,
    KEIN Crash (channel_scanner würde sonst die Phase verlieren)."""
    from app.utils import ytdlp_adapter as mod

    def boom(*a, **k):
        raise RuntimeError("This channel does not have a Shorts tab")

    monkeypatch.setattr(mod, "_ydl_extract", boom)
    ch = ChannelAdapter("https://www.youtube.com/@test")
    ch.html_url = ch.shorts_url
    result = list(ch.url_generator())
    assert result == []


def test_url_generator_yields_channel_video_items(monkeypatch):
    """Flat-Entries werden zu ChannelVideoItem mit den Feldern, die
    channel_scanner._extract liest (video_id, title, length, views,
    thumbnail_url, publish_date)."""
    from app.utils import ytdlp_adapter as mod

    fake_info = {
        "channel": "TestChan",
        "channel_id": "UCtest",
        "entries": [
            {"id": "vid1aaaaaaa", "title": "Erstes Video", "duration": 120,
             "view_count": 999, "upload_date": "20260101"},
            {"id": "vid2bbbbbbb", "title": "Zweites", "duration": 60},
            None,  # muss übersprungen werden
        ],
    }
    monkeypatch.setattr(mod, "_ydl_extract", lambda *a, **k: fake_info)
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


def test_url_generator_uses_web_client_and_desktop_ua(monkeypatch):
    """Channel-Tabs müssen mit festem web-Client + Desktop-UA laufen –
    sonst 'Unable to recognize tab page' + 4 sinnlose Retries."""
    from app.utils import ytdlp_adapter as mod
    captured = {}

    def spy(url, extra_opts=None, force_clients=None, desktop_ua_only=False):
        captured["force_clients"] = force_clients
        captured["desktop_ua_only"] = desktop_ua_only
        captured["extract_flat"] = (extra_opts or {}).get("extract_flat")
        return {"channel": "C", "channel_id": "UCx", "entries": []}

    monkeypatch.setattr(mod, "_ydl_extract", spy)
    ch = ChannelAdapter("https://www.youtube.com/@x")
    list(ch.url_generator())
    assert captured["force_clients"] == ["web"]
    assert captured["desktop_ua_only"] is True
    assert captured["extract_flat"] == "in_playlist"


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
    from app.utils import ytdlp_adapter as mod
    fake = {
        "channel": "C", "channel_id": "UCx",
        "entries": [
            {"_type": "playlist", "entries": [
                {"id": "nested1aaaa", "title": "N1"},
                {"id": "nested2bbbb", "title": "N2"},
            ]},
            {"id": "flat3cccccc", "title": "F3"},
        ],
    }
    monkeypatch.setattr(mod, "_ydl_extract", lambda *a, **k: fake)
    ch = ChannelAdapter("https://www.youtube.com/@x")
    ids = [v.video_id for v in ch.url_generator()]
    assert ids == ["nested1aaaa", "nested2bbbb", "flat3cccccc"]
