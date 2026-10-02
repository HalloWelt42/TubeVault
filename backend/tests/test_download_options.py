"""
Wirksame Download-Optionen (app/services/download_options.py).

Kontrakt: Für jede Option gilt Auftrag > Kanal > Einstellungen - an EINER
Stelle, für jeden Einstieg gleich. Aufgelöst wird beim Start des Downloads.
"""
import json

import pytest

from app.services import download_options
from app.services.download_service import download_service

VID = "abcdefghijk"
CH = "UCkanal0000000000000001"


@pytest.fixture
async def channel(test_db, set_setting):
    await set_setting("download.quality", "1080p")
    await set_setting("rss.auto_quality", "480p")

    async def _make(quality=None, audio_only=0):
        await test_db.execute(
            "INSERT INTO subscriptions (channel_id, channel_name, download_quality, audio_only) "
            "VALUES (?, 'Kanal', ?, ?)", (CH, quality, audio_only))
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, ?, 'T')", (VID, CH))
    return _make


async def test_standard_fuer_handstart(channel):
    eff = await download_options.effective(VID, {})
    assert (eff.quality, eff.quality_source) == ("1080p", "standard")


async def test_standard_fuer_automatik(channel):
    eff = await download_options.effective(VID, {"origin": "auto"})
    assert (eff.quality, eff.quality_source) == ("480p", "standard")


async def test_kanal_schlaegt_standard(channel):
    await channel(quality="720p")
    for requested in ({}, {"origin": "auto"}):
        eff = await download_options.effective(VID, requested)
        assert (eff.quality, eff.quality_source) == ("720p", "kanal")


async def test_kanal_ohne_qualitaet_erbt(channel):
    await channel(quality=None)
    assert (await download_options.effective(VID, {})).quality == "1080p"
    assert (await download_options.effective(VID, {"origin": "auto"})).quality == "480p"


async def test_auftrag_schlaegt_kanal(channel):
    await channel(quality="720p", audio_only=1)
    eff = await download_options.effective(VID, {"quality": "2160p"})
    assert (eff.quality, eff.quality_source, eff.audio_only) == ("2160p", "auftrag", False)


async def test_nur_audio_vom_kanal(channel):
    await channel(quality="720p", audio_only=1)
    eff = await download_options.effective(VID, {})
    assert eff.audio_only and eff.quality == "audio_only"


async def test_nur_audio_ausdruecklich_abgewaehlt(channel):
    await channel(audio_only=1)
    eff = await download_options.effective(VID, {"audio_only": False})
    assert not eff.audio_only and eff.quality == "1080p"


async def test_thumbnail_und_untertitel_aus_einstellungen(channel, set_setting):
    await set_setting("download.auto_thumbnail", "false")
    await set_setting("download.auto_subtitle", "true")
    await set_setting("download.subtitle_lang", "de, en")
    eff = await download_options.effective(VID, {})
    assert eff.download_thumbnail is False
    assert eff.subtitle_langs == ["de", "en"]

    eff = await download_options.effective(VID, {"download_thumbnail": True, "subtitle_lang": "fr"})
    assert eff.download_thumbnail is True
    assert eff.subtitle_langs == ["fr"]


async def test_auftrag_speichert_nur_ausdruecklich_gewaehltes(test_db, channel):
    result = await download_service.add_to_queue(f"https://www.youtube.com/watch?v={VID}")
    meta = json.loads(await test_db.fetch_val(
        "SELECT metadata FROM jobs WHERE id = ?", (result["job_id"],)))
    assert meta["download_options"] == {}, "nichts gewählt → nichts eingefroren"


async def test_geaenderte_einstellung_gilt_fuer_wartende_auftraege(test_db, channel, set_setting):
    result = await download_service.add_to_queue(f"https://www.youtube.com/watch?v={VID}")
    await set_setting("download.quality", "360p")
    meta = json.loads(await test_db.fetch_val(
        "SELECT metadata FROM jobs WHERE id = ?", (result["job_id"],)))
    eff = await download_options.effective(VID, meta["download_options"])
    assert eff.quality == "360p"


class _S:
    def __init__(self, res):
        self.resolution = f"{res}p"


def _pick(quality, progressive, separate):
    p = _S(progressive) if progressive else None
    s = _S(separate) if separate else None
    chosen = download_service._closest_to_wish(quality, p, s)
    return (int(chosen.resolution[:-1]), "getrennt" if chosen is s else "fertig")


def test_qualitaetswahl_trifft_den_wunsch():
    # Der frühere Fehler: 720p gewünscht, fertiger Stream nur 360p → es kam 360p
    assert _pick("720p", 360, 720) == (720, "getrennt")
    assert _pick("480p", 360, 480) == (480, "getrennt")
    # Fertiger Stream reicht → kein Merge nötig
    assert _pick("360p", 360, 360) == (360, "fertig")
    # Nie mehr als gewünscht
    assert _pick("240p", 360, 240) == (240, "getrennt")
    assert _pick("best", 360, 2160) == (2160, "getrennt")
    # Wunsch nicht verfügbar → das Nächstkleinere
    assert _pick("1080p", 360, 720) == (720, "getrennt")
