"""
YouTube-Suche: Blättern über eine zwischengespeicherte Trefferliste.

Kontrakt:
- Seiten überlappen nicht und lassen nichts aus, auch wenn die Quelle bei
  jedem Abruf eine andere Reihenfolge liefert.
- Shorts stehen nur unter shorts, nie zusätzlich unter videos.
- Folgeseiten lösen keinen neuen Abruf aus, solange der Vorrat reicht.
"""
import random

import pytest

from app.routers import search as search_router


class _Item:
    def __init__(self, n, length):
        self.video_id = f"vid{n:04d}"
        self.title = f"Treffer {n}"
        self.author = "Kanal"
        self.channel_id = "UCx"
        self.length = length
        self.views = n
        self.thumbnail_url = ""


class _FakeSearch:
    calls = 0
    available = 120

    def __init__(self, query, max_results=25, **_):
        type(self).calls += 1
        items = [_Item(n, 30 if n % 5 == 0 else 600) for n in range(self.available)]
        random.shuffle(items)   # Quelle liefert jedes Mal eine andere Reihenfolge
        self.videos = items[:max_results]
        self.playlist = []
        self.channel = []
        self.completion_suggestions = []


@pytest.fixture
def fake_source(monkeypatch):
    import app.utils.pytube_client as client
    _FakeSearch.calls = 0
    _FakeSearch.available = 120
    monkeypatch.setattr(client, "make_search", _FakeSearch)
    search_router._yt_cache.clear()
    yield _FakeSearch
    search_router._yt_cache.clear()


def test_seiten_ohne_ueberlappung(fake_source):
    seen = []
    page = 1
    while True:
        r = search_router._do_yt_search("test", include_extras=True, page=page, per_page=20)
        seen += [v["id"] for v in r["videos"]]
        if not r["has_more"]:
            break
        page += 1
        assert page < 20
    assert len(seen) == len(set(seen)), "kein Treffer doppelt"
    assert len(seen) == 96, "alle langen Videos (120 minus 24 Shorts) erreichbar"


def test_shorts_nicht_doppelt(fake_source):
    r = search_router._do_yt_search("test", include_extras=True, page=1, per_page=20)
    video_ids = {v["id"] for v in r["videos"]}
    short_ids = {v["id"] for v in r["shorts"]}
    assert short_ids and not (video_ids & short_ids)
    assert all(v["duration"] > 60 for v in r["videos"])


def test_folgeseite_ohne_neuen_abruf(fake_source):
    search_router._do_yt_search("Test  Begriff", include_extras=True, page=1, per_page=10)
    calls = fake_source.calls
    # gleiche Anfrage (andere Schreibweise) und nächste Seite aus dem Vorrat
    search_router._do_yt_search("test begriff", include_extras=True, page=1, per_page=10)
    assert fake_source.calls == calls


def test_wenige_treffer_enden_sauber(fake_source):
    fake_source.available = 7
    r = search_router._do_yt_search("selten", include_extras=True, page=1, per_page=20)
    assert r["has_more"] is False
    assert len(r["videos"]) + len(r["shorts"]) == 7
    r2 = search_router._do_yt_search("selten", include_extras=True, page=2, per_page=20)
    assert r2["videos"] == [] and r2["has_more"] is False
