"""Transkripte: lokal erkennen lassen, zerlegen, im Volltext und nach Bedeutung finden."""
import pytest

from app.services import search_index, semantic_index, transcripts
from app.services.subtitle_segments import Segment

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


async def test_transkript_fuer_nachvertonung(stock, monkeypatch, tmp_path):
    """Die Nachvertonung bekommt nur, was schon da ist - bei der Quelle wird
    nichts geholt. Fehlt es, transkribiert der Vertonungsdienst selbst."""
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)
    folder = tmp_path / "vidloeten01"
    folder.mkdir()
    (folder / "de.vtt").write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nErst das Zinn.\n\n"
        "00:00:03.000 --> 00:00:05.000\nDann die Spitze.\n", encoding="utf-8")
    answer = await transcripts.for_dubbing("vidloeten01", "manual")
    assert answer.transcript.kind == "manual"
    assert [s.text for s in answer.transcript.segments] == ["Erst das Zinn.", "Dann die Spitze."]

    assert "noch kein Transkript" in (await transcripts.for_dubbing("vidkochen1", "any")).reason
    assert (await transcripts.for_dubbing("vidloeten01", "never")).transcript is None
    await stock.execute("UPDATE transcripts SET kind = 'ai' WHERE video_id = 'vidloeten01'")
    assert "KI-Transkript" in (await transcripts.for_dubbing("vidloeten01", "manual")).reason
    assert "fehlt" in (await transcripts.for_dubbing("vidloeten01", "any")).reason


# ─── KI-Transkripte ───────────────────────────────────────────────────

async def test_ki_transkript_fuer_videos_ohne_transkript(stock, monkeypatch, tmp_path):
    """Jedes Video ohne Transkript wartet auf die Spracherkennung; das
    abgelieferte Transkript ist durchsuchbar und überall als KI-Transkript
    gekennzeichnet (Datei "ki.<sprache>.vtt", Art "ai")."""
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)

    assert await transcripts.pending() == 1          # das Lötvideo hat schon eines
    job = await transcripts.claim_ai("mac")
    assert job.video_id == "vidkochen1" and job.language is None
    assert await transcripts.claim_ai("mac") is None             # nur einmal vergeben
    assert await transcripts.heartbeat_ai("vidkochen1", "Transkribieren")

    result = transcripts.AiResult(language="de", segments=[
        Segment(start=0, end=3, text="Zuerst kommt das Salz."),
        Segment(start=3, end=6, text="Dann der Pfeffer."),
    ])
    assert await transcripts.finish_ai("vidkochen1", result) == 1
    vtt = (tmp_path / "vidkochen1" / "ki.de.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and "KI-Transkript" in vtt and "00:00:03.000" in vtt
    assert await stock.fetch_val("SELECT language FROM videos WHERE id = 'vidkochen1'") == "de"

    found = (await search_index.search_videos("Pfeffer"))["videos"]
    assert found[0]["id"] == "vidkochen1" and found[0]["passage"]["kind"] == "ai"
    assert (await transcripts.ai_counts())["done"] == 1
    assert await transcripts.pending() == 0

    # Verspätetes Abliefern zu einem nicht mehr laufenden Auftrag wird abgelehnt
    with pytest.raises(ValueError):
        await transcripts.finish_ai("vidkochen1", result)


async def test_untertitel_liste_nennt_die_herkunft(async_client_factory, stock, monkeypatch, tmp_path):
    from app import config
    monkeypatch.setattr(config, "SUBTITLES_DIR", tmp_path)
    from app.routers import player
    client = await async_client_factory(player.router)
    folder = tmp_path / "vidkochen1"
    folder.mkdir()
    for name in ("de.vtt", "a.en.vtt", "ki.de.vtt"):
        (folder / name).write_text("WEBVTT\n", encoding="utf-8")
    listed = {s["code"]: (s["kind"], s["name"]) for s in
              (await client.get("/api/player/vidkochen1/subtitles")).json()["subtitles"]}
    assert listed["ki.de"] == ("ai", "Deutsch - KI-Transkript")
    assert listed["a.en"][0] == "auto" and listed["de"][0] == "manual"


async def test_musik_kommt_nicht_zur_ki(stock):
    await stock.execute("UPDATE videos SET is_music = 1 WHERE id = 'vidkochen1'")
    assert await transcripts.claim_ai("mac") is None


async def test_neueste_zuerst_neu_geladene_draengeln_vor(stock):
    """Vergeben wird immer das zuletzt geladene Video ohne Transkript; kommt
    ein neues hinzu, ist es als nächstes dran, danach geht es mit den
    nächstälteren weiter."""
    for video_id, day in (("alt0000001", "2026-01-01"), ("mitte00001", "2026-05-01")):
        await stock.execute(
            "INSERT INTO videos (id, title, status, download_date) VALUES (?, 'x', 'ready', ?)",
            (video_id, day))
    await stock.execute("UPDATE videos SET download_date = '2025-01-01' WHERE id = 'vidkochen1'")
    assert (await transcripts.claim_ai("mac")).video_id == "mitte00001"
    await transcripts.fail_ai("mitte00001", "Testfehler")
    await stock.execute(
        "INSERT INTO videos (id, title, status, download_date) VALUES ('neu0000001', 'x', 'ready', '2026-10-06')")
    assert (await transcripts.claim_ai("mac")).video_id == "neu0000001"
    assert (await transcripts.claim_ai("mac")).video_id == "alt0000001"
    assert (await transcripts.claim_ai("mac")).video_id == "vidkochen1"
    assert await transcripts.claim_ai("mac") is None      # Gescheiterte nicht endlos wiederholen


async def test_verwaister_auftrag_kommt_zurueck(stock):
    assert (await transcripts.claim_ai("mac")).video_id == "vidkochen1"
    await stock.execute("UPDATE ai_transcriptions SET heartbeat_at = datetime('now', '-2 hours')")
    assert (await transcripts.claim_ai("mac")).video_id == "vidkochen1"
