"""Untertitel der Quelle als Transkript für die Nachvertonung."""
from app.services import subtitle_segments as subs

MANUAL = """WEBVTT

00:00:01.000 --> 00:00:03.000
Welcome to the workshop,

00:00:03.000 --> 00:00:05.500
today we build a <i>shelf</i>.

00:00:09.000 --> 00:00:11.000
First &amp; foremost: safety

00:00:11.000 --> 00:00:12.000
glasses on!
"""

# Automatisch erzeugt: jede Zeile erscheint zweimal, dazwischen 10-ms-Einträge
AUTO = """WEBVTT

00:00:00.000 --> 00:00:02.000
hello and welcome

00:00:02.000 --> 00:00:02.010
hello and welcome

00:00:02.010 --> 00:00:04.000
hello and welcome
to the channel

00:00:04.000 --> 00:00:04.010
to the channel

00:00:04.010 --> 00:00:06.000
to the channel
today we solder
"""


def test_eintraege_lesen_ohne_auszeichnung():
    cues = subs.parse_vtt(MANUAL)
    assert len(cues) == 4
    assert (cues[1].start, cues[1].end, cues[1].text) == (3.0, 5.5, "today we build a shelf.")
    assert cues[2].text == "First & foremost: safety"
    srt = "1\n00:01:02,500 --> 00:01:04,000\nKomma als Trenner\n"
    assert subs.parse_vtt(srt)[0].start == 62.5


def test_zeilen_werden_zu_saetzen():
    sentences = subs.into_sentences(subs.without_repeats(subs.parse_vtt(MANUAL)))
    assert [(s.start, s.end, s.text) for s in sentences] == [
        (1.0, 5.5, "Welcome to the workshop, today we build a shelf."),
        (9.0, 12.0, "First & foremost: safety glasses on!"),
    ]


def test_sprechpause_und_hoechstdauer_trennen():
    cues = [subs.Segment(start=n * 4.0, end=n * 4.0 + 4, text=f"teil {n}") for n in range(6)]
    cues.append(subs.Segment(start=40.0, end=42.0, text="nach der pause"))
    sentences = subs.into_sentences(cues)
    assert all(s.end - s.start <= subs.MAX_SEGMENT_SECONDS for s in sentences)
    assert sentences[-1].text == "nach der pause"
    assert " ".join(s.text for s in sentences[:-1]) == " ".join(f"teil {n}" for n in range(6))


def test_automatische_untertitel_ohne_wiederholungen():
    cues = subs.without_repeats(subs.parse_vtt(AUTO))
    assert " ".join(c.text for c in cues) == "hello and welcome to the channel today we solder"
