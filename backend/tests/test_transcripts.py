"""Transkripte: holen, zerlegen, im Volltext und nach Bedeutung finden."""
import pytest

from app.services import search_index, semantic_index, transcripts
from app.services.subtitle_segments import Segment
from app.utils.ytdlp_adapter import pick_caption

VTT = [{"ext": "json3", "url": "j"}, {"ext": "vtt", "url": "v"}]


def test_untertitel_wahl():
    # Vom Autor erstellte in der Originalsprache gewinnen
    choice = pick_caption({"language": "en", "subtitles": {"en-GB": VTT, "de": VTT},
                           "automatic_captions": {"en-orig": VTT, "en": VTT, "de": VTT}})
    assert (choice.language, choice.kind, choice.url) == ("en", "manual", "v")
    # Sonst die automatisch erzeugten des Originals, nie eine Übersetzung
    choice = pick_caption({"subtitles": {}, "automatic_captions": {"de-orig": VTT, "en": VTT, "de": VTT}})
    assert (choice.language, choice.kind) == ("de", "auto")
    assert pick_caption({"language": "fr", "subtitles": {"de": VTT}, "automatic_captions": {"en": VTT}}) is None
    assert pick_caption({"subtitles": {"live_chat": VTT}}) is None
    # Sprache unbekannt: die Angabe am Video hilft
    assert pick_caption({"automatic_captions": {"en": VTT}}, "en").kind == "auto"


def test_saetze_werden_zu_abschnitten():
    sentences = [Segment(start=n * 5.0, end=n * 5.0 + 5, text="wort " * 40) for n in range(10)]
    chunks = transcripts.into_chunks(sentences)
    assert 1 < len(chunks) < 10
    assert all(len(chunk.text) <= transcripts.CHUNK_CHARS for chunk in chunks)
    assert chunks[0].start == 0 and chunks[-1].end == 50
    assert chunks[1].start == chunks[0].end


@pytest.fixture
async def stock(test_db):
    for video_id, title in (("vidloeten01", "Werkbank Folge 12"), ("vidkochen1", "Küche Folge 3")):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, source) VALUES (?, ?, 'ready', 'youtube')",
            (video_id, title))
    await transcripts.store("vidloeten01", "de", "manual", [
        Segment(start=0, end=4, text="Willkommen in der Werkstatt."),
        *[Segment(start=10 + n, end=11 + n, text="Füllsatz " * 30) for n in range(3)],
        Segment(start=600, end=606, text="Jetzt verzinnen wir die Lötspitze mit frischem Zinn."),
    ])
    return test_db


async def test_wort_im_transkript_findet_video_mit_stelle(stock):
    result = await search_index.search_videos("Lötspitze")
    assert [v["id"] for v in result["videos"]] == ["vidloeten01"]
    passage = result["videos"][0]["passage"]
    assert "Lötspitze" in passage["text"] and passage["start"] == 600
    # Ohne Treffer im Transkript bleibt es bei der bisherigen Suche
    assert (await search_index.search_videos("Küche"))["videos"][0]["id"] == "vidkochen1"
    assert "passage" not in (await search_index.search_videos("Küche"))["videos"][0]


async def test_bedeutung_im_transkript(stock, set_setting, monkeypatch):
    async def fake_embed(texts, url, model, timeout):
        return [[1.0, 0.0] if ("Zinn" in t or "Lot" in t) else [0.0, 1.0] for t in texts]
    monkeypatch.setattr(semantic_index, "_embed", fake_embed)

    async def reachable():
        return True
    monkeypatch.setattr(semantic_index, "available", reachable)
    monkeypatch.setattr(semantic_index, "_chunk_vectors", semantic_index._ChunkVectors())
    semantic_index._query_cache.clear()
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://ki.test/v1")

    cfg = await semantic_index.config()
    assert await semantic_index.pending_chunks(cfg[1]) > 0
    while await semantic_index.index_chunk_batch(*cfg):
        pass
    assert await semantic_index.pending_chunks(cfg[1]) == 0

    hits = await semantic_index.search_passages("Lot auftragen")
    by_id = await transcripts.passages_by_id([chunk_id for chunk_id, _ in hits])
    assert len(hits) == 1 and "Zinn" in by_id[hits[0][0]].text

    result = await search_index.search_videos("Lot auftragen")
    assert result["videos"][0]["id"] == "vidloeten01"
    assert result["videos"][0]["match"] == "bedeutung"
    assert "Zinn" in result["videos"][0]["passage"]["text"]


async def test_abruf_speichert_oder_vermerkt_fehlen(stock, monkeypatch, tmp_path):
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)
    from app.utils.ytdlp_adapter import CaptionChoice
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSalz und Pfeffer dazu.\n"
    answers = {"vidkochen1": (CaptionChoice("de", "auto", "u"), vtt)}
    monkeypatch.setattr(transcripts, "_download_caption",
                        lambda video_id, language: answers.get(video_id, (None, None)))

    assert await transcripts.pending() == 1          # das Lötvideo hat schon eines
    result = await transcripts.fetch("vidkochen1")
    assert (result.status, result.kind, result.chunks) == ("ok", "auto", 1)
    assert (tmp_path / "vidkochen1" / "a.de.vtt").exists()
    assert await transcripts.pending() == 0

    await stock.execute("INSERT INTO videos (id, title, status, source) VALUES ('ohnetext01', 'x', 'ready', 'youtube')")
    assert (await transcripts.fetch("ohnetext01")).status == "none"
    assert await transcripts.pending() == 0          # wird nicht immer wieder gefragt

    # Löschen des Videos nimmt Transkript und Abschnitte mit
    await stock.execute("DELETE FROM videos WHERE id = 'vidkochen1'")
    assert await stock.fetch_val("SELECT COUNT(*) FROM transcript_chunks WHERE video_id = 'vidkochen1'") == 0
    assert (await search_index.search_videos("Pfeffer"))["videos"] == []


async def test_transkript_fuer_nachvertonung(stock, monkeypatch, tmp_path):
    """Die Sprache des Originals muss am Video nicht bekannt sein: die Quelle
    bestimmt sie, und das Video lernt sie dabei. (Fehler: ohne bekannte Sprache
    gab es nie ein Transkript, der Vertonungsdienst transkribierte alles selbst.)"""
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)
    from app.utils.ytdlp_adapter import CaptionChoice
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nFirst we add salt.\n\n00:00:03.000 --> 00:00:05.000\nThen pepper.\n"
    calls = []

    def download(video_id, language):
        calls.append(video_id)
        if video_id == "vidkochen1":
            return CaptionChoice("en", "auto", "u"), vtt
        return None, None
    monkeypatch.setattr(transcripts, "_download_caption", download)

    assert await stock.fetch_val("SELECT language FROM videos WHERE id = 'vidkochen1'") is None
    answer = await transcripts.for_dubbing("vidkochen1", "any")
    assert answer.transcript.language == "en" and answer.transcript.kind == "auto"
    assert [s.text for s in answer.transcript.segments] == ["First we add salt.", "Then pepper."]
    assert await stock.fetch_val("SELECT language FROM videos WHERE id = 'vidkochen1'") == "en"

    # Zweite Anfrage: nichts wird erneut geholt
    await transcripts.for_dubbing("vidkochen1", "any")
    assert calls == ["vidkochen1"]

    # Gründe, wenn es keines gibt - der Vertonungsdienst transkribiert dann selbst
    assert "automatisch" in (await transcripts.for_dubbing("vidkochen1", "manual")).reason
    assert (await transcripts.for_dubbing("vidkochen1", "never")).transcript is None
    await stock.execute("INSERT INTO videos (id, title, status, source) VALUES ('ohnetext01', 'x', 'ready', 'youtube')")
    assert "keine Untertitel" in (await transcripts.for_dubbing("ohnetext01", "any")).reason

    def broken(video_id, language):
        raise RuntimeError("HTTP Error 429: Too Many Requests")
    monkeypatch.setattr(transcripts, "_download_caption", broken)
    await stock.execute("INSERT INTO videos (id, title, status, source) VALUES ('gebremst01', 'x', 'ready', 'youtube')")
    assert "429" in (await transcripts.for_dubbing("gebremst01", "any")).reason
