"""
Original-Tonspur erkennen (ytdlp_adapter.keep_original_audio).

Fehlerbild: Deutsche Videos wurden manchmal mit der englischen, automatisch
übersetzten Tonspur geladen - die Auswahl nahm "bestes Audio" über ALLE
Sprachen.
"""
from app.utils.ytdlp_adapter import (
    StreamAdapter, StreamQueryAdapter, keep_original_audio, original_audio_language,
)


def _audio(fid, lang, abr, note="", pref=None):
    return {"format_id": fid, "acodec": "mp4a.40.2", "vcodec": "none", "ext": "m4a",
            "language": lang, "abr": abr, "format_note": note, "language_preference": pref,
            "url": "x"}


def _video(fid, height):
    return {"format_id": fid, "acodec": "none", "vcodec": "avc1", "ext": "mp4",
            "height": height, "url": "x"}


DUBBED = [
    _video("137", 1080),
    _audio("140-0", "en-US", 160, "English (US), high", pref=-1),      # Übersetzung, höhere Bitrate!
    _audio("140-1", "de", 128, "Deutsch original, medium", pref=10),
    _audio("251-0", "fr", 160, "French, high", pref=-1),
    {"format_id": "18", "acodec": "mp4a.40.2", "vcodec": "avc1", "ext": "mp4", "height": 360,
     "language": "en-US", "format_note": "360p", "url": "x"},            # fertiger Stream mit Übersetzung
]


def test_original_per_hinweis():
    assert original_audio_language(DUBBED, "de") == "de"


def test_original_per_praeferenz_ohne_hinweis():
    fmts = [_audio("a", "en", 160, "high", pref=5), _audio("b", "de", 128, "medium", pref=10)]
    assert original_audio_language(fmts, None) == "de"


def test_original_per_videosprache():
    fmts = [_audio("a", "en", 160), _audio("b", "de-DE", 128)]
    assert original_audio_language(fmts, "de") == "de"


def test_nicht_bestimmbar_laesst_alles():
    fmts = [_audio("a", "en", 160), _audio("b", "de", 128)]
    assert original_audio_language(fmts, None) is None
    assert keep_original_audio(fmts, None) == fmts


def test_einsprachig_unveraendert():
    fmts = [_video("137", 1080), _audio("140", "en", 128), _audio("251", "en", 160)]
    assert keep_original_audio(fmts, "en") == fmts
    assert original_audio_language(fmts, None) == "en"


def test_uebersetzte_spuren_fliegen_raus():
    kept = {f["format_id"] for f in keep_original_audio(DUBBED, "de")}
    assert kept == {"137", "140-1"}, "auch der fertige Stream mit Übersetzung fällt weg"


def test_bestes_audio_ist_das_original():
    streams = StreamQueryAdapter([StreamAdapter(f) for f in keep_original_audio(DUBBED, "de")])
    assert streams.get_audio_only().itag == "140-1"


def test_formate_ohne_sprachangabe_bleiben():
    fmts = [_audio("a", None, 160), _audio("b", "de", 128, "original"), _audio("c", "en", 128)]
    assert {f["format_id"] for f in keep_original_audio(fmts, "de")} == {"a", "b"}
