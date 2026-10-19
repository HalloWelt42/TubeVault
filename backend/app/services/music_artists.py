"""
TubeVault – Namen der Interpreten

Ein Titel kann mehrere Interpreten nennen ("50 Cent, Nate Dogg", "Daft Punk
feat. Pharrell Williams"). Entschieden 19.10.2026 ("Bei jedem Genannten",
"Automatisch und Liste"): Der Titel zählt bei jedem Genannten - er steht in der
Gruppe und Wiedergabeliste jedes Namens; angezeigt wird weiter die Angabe, wie
sie im Tag steht. Naming.names() ist die eine Stelle, die sagt, wen ein Titel
nennt.

Getrennt wird an ", " und an " feat. ", " ft. ", " featuring " (Groß- und
Kleinschreibung egal), nie an "&": "Kool & The Gang" und "Daryl Hall & John
Oates" bleiben ganz.

Bandschutz: Auch Bandnamen tragen Kommas ("Earth, Wind & Fire", "Crosby,
Stills, Nash & Young"). Eine Angabe wird nur getrennt, wenn mindestens einer
ihrer Teile für sich als Interpret vorkommt - in den Musikdateien (Interpret
oder Album-Interpret) oder als Interpret eines Musikvideos. "Earth" kommt nie
allein vor, also bleibt "Earth, Wind & Fire" ganz. Was eine Trennung ergibt,
kommt danach ebenso als Interpret vor ("50 Cent, Akon" bringt "Akon", dann
trennt auch "Akon, Kardinal Offishall"); das läuft, bis sich nichts mehr
ändert. Gemessen am Bestand 19.10.2026: 754 Angaben mit mehreren Teilen, nur
mit den allein stehenden Namen blieben 304 ganz (darunter jede Angabe "David
Guetta, ..."), so 212. Eine ganz gebliebene Angabe bleibt auch in längeren
ganz: "Earth, Wind & Fire, The Emotions" nennt "Earth, Wind & Fire" und "The
Emotions".

Dazu zwei Listen in den Einstellungen: nie trennen (bleibt ganz, auch wenn
ein Teil allein vorkommt; gilt vor immer trennen) und immer trennen (auch
ohne bekannten Teil). Vorschläge für beide liefert suggestions(): die
erkannten Bandnamen und die getrennten Angaben, meiste Titel zuerst.

Gerechnet wird einmal je Datenstand der Datenbank (shared_cache.for_version).
"""
import json
import re
from collections import Counter
from typing import Iterable

from app.database import db
from app.services import music_files, setting_values, shared_cache
from app.services.music_keys import group_key

WHOLE = "music.artists_whole"         # Einstellung: nie trennen
SPLIT = "music.artists_split"         # Einstellung: immer trennen
UNKNOWN = "Unbekannt"
SEPARATOR = re.compile(r",\s+|\s+(?:feat|ft)\.\s+|\s+featuring\s+", re.IGNORECASE)
_CACHE_KEY = "music_artist_names"


def _spans(raw: str) -> list[tuple[int, int]]:
    """Teile einer Angabe als (Anfang, Ende) im Original; leere fallen weg."""
    spans, start = [], 0
    for match in SEPARATOR.finditer(raw):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(raw)))
    return [(a, b) for a, b in spans if raw[a:b].strip()]


def _joined(raw: str, spans: list[tuple[int, int]], whole: set[str]) -> list[str]:
    """Namen einer Angabe: ihre Teile, wobei aufeinanderfolgende Teile, die
    zusammen ein ganz bleibender Name sind, zusammenbleiben (längster zuerst).
    Jeder Name steht so im Original."""
    names, i = [], 0
    while i < len(spans):
        end = i + 1
        for j in range(len(spans), i + 1, -1):
            if (j - i) < len(spans) and group_key(raw[spans[i][0]:spans[j - 1][1]]) in whole:
                end = j
                break
        names.append(raw[spans[i][0]:spans[end - 1][1]].strip())
        i = end
    return names


class Naming:
    """Wen eine Angabe nennt; gebaut aus allen Interpreten des Bestands."""

    def __init__(self, known: set[str], whole: set[str], always: set[str],
                 bands: dict[str, tuple[str, int]], split: dict[str, tuple[str, int]]):
        self.known = known                # Schlüssel der Namen, die als Interpret vorkommen
        self.whole = whole                # bleiben ganz: nie trennen und erkannte Bandnamen
        self.always = always              # immer trennen
        self.bands = bands                # erkannte Bandnamen: Schlüssel -> (Schreibweise, Titel)
        self.split = split                # getrennte Angaben: Schlüssel -> (Schreibweise, Titel)

    def names(self, raw: str) -> list[str]:
        """Die Genannten einer Angabe, in ihrer Reihenfolge und Schreibweise;
        ohne Trennung die Angabe selbst."""
        raw = raw.strip()
        spans = _spans(raw)
        key = group_key(raw)
        if len(spans) < 2 or key in self.whole:
            return [raw]
        if key not in self.always and not any(group_key(raw[a:b]) in self.known for a, b in spans):
            return [raw]
        unique: dict[str, str] = {}
        for name in _joined(raw, spans, self.whole):
            unique.setdefault(group_key(name), name)
        return list(unique.values())


def build(credits: Counter, extra: Iterable[str] = (), never: Iterable[str] = (),
          always: Iterable[str] = ()) -> Naming:
    """credits: Angabe je Titel (gezählt), extra: weitere Namen, die als
    Interpret vorkommen (Album-Interpret), never/always: die Listen."""
    never_keys = {group_key(n) for n in never if n.strip()}
    always_keys = {group_key(n) for n in always if n.strip()} - never_keys
    spellings: dict[str, str] = {}
    counts: Counter = Counter()
    for raw, count in credits.items():
        if raw and raw.strip():
            spellings.setdefault(group_key(raw), raw.strip())
            counts[group_key(raw)] += count
    for raw in extra:
        if raw and raw.strip():
            spellings.setdefault(group_key(raw), raw.strip())
    multi = {key: (raw, spans) for key, raw in spellings.items() if len(spans := _spans(raw)) > 1}
    known = {key for key in spellings if key not in multi}
    while True:
        whole = never_keys | {key for key, (raw, spans) in multi.items()
                              if key not in always_keys and not any(group_key(raw[a:b]) in known for a, b in spans)}
        grown = known | {group_key(name) for key, (raw, spans) in multi.items() if key not in whole
                         for name in _joined(raw, spans, whole)}
        if grown == known:
            break
        known = grown
    bands = {key: (multi[key][0], counts[key]) for key in whole if key in multi and key not in never_keys}
    split = {key: (raw, counts[key]) for key, (raw, _) in multi.items() if key not in whole}
    return Naming(known, whole, always_keys, bands, split)


def listed(value: str) -> list[str]:
    """Namen einer Liste aus den Einstellungen (JSON); Unlesbares zählt als leer."""
    try:
        names = json.loads(value or "[]")
    except ValueError:
        return []
    return [n for n in names if isinstance(n, str) and n.strip()] if isinstance(names, list) else []


async def naming() -> Naming:
    """Namen aus dem ganzen Bestand und den Listen, einmal je Datenstand."""
    return await shared_cache.for_version(_CACHE_KEY, await db.data_version(), _load)


async def _load() -> Naming:
    from app.services.music_library import names_of   # Interpret eines Musikvideos (dort die eine Regel)
    credits: Counter = Counter()
    extra = set()
    for row in await db.fetch_all(
            "SELECT artist, album_artist FROM music_files WHERE COALESCE(category, ?) = ?",
            (music_files.MUSIC, music_files.MUSIC)):
        credits[(row["artist"] or row["album_artist"] or UNKNOWN).strip()] += 1
        if row["album_artist"]:
            extra.add(row["album_artist"])
    for row in await db.fetch_all(
            """SELECT id, title, music_artist, music_title, channel_name FROM videos
               WHERE status = 'ready' AND is_music = 1 AND COALESCE(is_audiobook, 0) = 0"""):
        credits[names_of(row)[0]] += 1
    credits.pop(UNKNOWN, None)
    return build(credits, extra, listed(await setting_values.get(WHOLE)), listed(await setting_values.get(SPLIT)))


async def suggestions(key: str) -> dict:
    """Vorschläge für eine der Listen ({options: [{value, label, hint}], state}),
    meiste Titel zuerst: für nie trennen die getrennten Angaben und die erkannten
    Bandnamen, für immer trennen die erkannten Bandnamen."""
    current = await naming()
    found = [(raw, count, "wird getrennt") for raw, count in current.split.values()] if key == WHOLE else []
    found += [(raw, count, "bleibt ganz") for raw, count in current.bands.values()]
    found.sort(key=lambda item: (-item[1], item[0].casefold()))
    options = [{"value": raw, "label": raw, "hint": f"{hint}, {count} Titel" if count else hint}
               for raw, count, hint in found]
    bands = f"{len(current.bands)} erkannte Bandnamen" if len(current.bands) != 1 else "1 erkannter Bandname"
    split = f"{len(current.split)} getrennte Angaben" if len(current.split) != 1 else "1 getrennte Angabe"
    return {"options": options, "state": f"{bands}, {split}"}
