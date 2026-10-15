"""
TubeVault – Eigene Videos: Abgleich mit Bibliothek und Feed

Reine Rechenlogik ohne Datenbank und Platte: ein Index aus Bibliothek
(fertig geladene Videos) und Feed (bekannte Videos der Abos), dagegen die
Angaben einer Datei. Der Index entsteht einmal je Einlesen; der Abgleich je
Datei schaut nur in kleine Ausschnitte (gleiche Dauer, gleicher Titel,
vermuteter Kanal) und bleibt dadurch auch bei zehntausenden Dateien schnell.

Reihenfolge der Regeln, die erste trifft:
  1. Kennung der Quelle im Dateinamen   -> schon vorhanden / sicher erkannt
  2. Bibliotheksvideo mit gleicher Dauer (+-2 s) und gleicher Größe oder
     gleichem Titel                      -> schon vorhanden
  3. Feed-Eintrag mit gleichem Titel und gleicher Dauer -> sicher erkannt,
     gleicher Titel ohne Dauer zum Vergleich             -> vermutlich
  4. ähnlicher Titel im vermuteten Kanal -> vermutlich
  5. sonst unbekannt
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz

from app.models.own_files import Finding, Match, MatchReason
from app.services.own_inventory import FileFacts

DURATION_TOLERANCE_S = 2
SAME_TITLE_RATIO = 85        # Titel gleicher Dauer gelten ab hier als gleich
SIMILAR_TITLE_RATIO = 88     # ähnlicher Titel im vermuteten Kanal
_QUALITY_TAG = re.compile(r"\((?:\d{3,4}p|\d+x\d+)[^)]*\)", re.IGNORECASE)
_NOT_WORD = re.compile(r"[\W_]+", re.UNICODE)


def loose_title(title: Optional[str]) -> str:
    """Titel nur aus Wörtern: Satzzeichen und Ersatzzeichen der Dateinamen
    ("_" statt "|" oder "?") spielen beim Vergleich keine Rolle."""
    return _NOT_WORD.sub(" ", _QUALITY_TAG.sub(" ", title or "")).strip().casefold()


def channel_key(name: Optional[str]) -> str:
    """Kanalname zum Vergleich mit Ordnernamen ("c't 3003" = "CT3003")."""
    return re.sub(r"[\W_]+", "", (name or "").casefold())


@dataclass(frozen=True)
class KnownVideo:
    """Ein Video aus Bibliothek (in_library) oder Feed."""
    id: str
    title: str
    channel_id: Optional[str]
    channel_name: Optional[str]
    duration: Optional[int]
    size: Optional[int] = None
    in_library: bool = False


def _close(a: Optional[int], b: Optional[int]) -> bool:
    return a is not None and b is not None and abs(a - b) <= DURATION_TOLERANCE_S


def _contradicts(a: Optional[int], b: Optional[int]) -> bool:
    """Beide Dauern bekannt und deutlich verschieden: sicher nicht dasselbe Video."""
    return a is not None and b is not None and abs(a - b) > DURATION_TOLERANCE_S


class MatchIndex:
    def __init__(self, library: Iterable[KnownVideo], feed: Iterable[KnownVideo],
                 channels: Iterable[tuple[str, str]]):
        """channels: (channel_id, Name) aller Abos und Bibliothekskanäle."""
        self.by_id: dict[str, KnownVideo] = {}
        self.by_duration: dict[int, list[KnownVideo]] = defaultdict(list)
        self.by_title: dict[str, list[KnownVideo]] = defaultdict(list)
        self.by_channel: dict[str, list[tuple[str, KnownVideo]]] = defaultdict(list)
        self.channel_ids: dict[str, str] = {}
        self.channel_names: dict[str, str] = {}
        for channel_id, name in channels:
            if channel_id and name:
                self.channel_ids.setdefault(channel_key(name), channel_id)
                self.channel_names.setdefault(channel_id, name)
        for video in library:
            self._add(video)
            if video.duration:
                self.by_duration[video.duration].append(video)
        for video in feed:
            if video.id not in self.by_id:   # die Bibliothek hat Vorrang
                self._add(video)

    def _add(self, video: KnownVideo) -> None:
        self.by_id[video.id] = video
        title = loose_title(video.title)
        if title:
            self.by_title[title].append(video)
            if video.channel_id:
                self.by_channel[video.channel_id].append((title, video))

    def channel_for(self, hint: Optional[str]) -> Optional[str]:
        """Kanal-Kennung zu einem Ordner- oder Kanalnamen."""
        return self.channel_ids.get(channel_key(hint)) if hint else None

    def same_duration(self, duration: int) -> list[KnownVideo]:
        return [v for d in range(duration - DURATION_TOLERANCE_S, duration + DURATION_TOLERANCE_S + 1)
                for v in self.by_duration.get(d, ())]


def _result(finding: Finding, reason: MatchReason, video: KnownVideo) -> Match:
    return Match(finding=finding, reason=reason, video_id=video.id, title=video.title,
                 channel_name=video.channel_name, duration=video.duration, size=video.size,
                 in_library=video.in_library)


def match(facts: FileFacts, index: MatchIndex) -> Match:
    title = loose_title(facts.title)
    channel_id = index.channel_for(facts.channel_hint)

    # 1. Kennung der Quelle (eine nur mögliche Kennung zählt, wenn sie bekannt ist)
    if facts.source_id:
        known = index.by_id.get(facts.source_id)
        if known:
            finding = Finding.DUPLICATE if known.in_library else Finding.CERTAIN
            return _result(finding, MatchReason.SOURCE_ID, known)
        if facts.source_id_certain:
            return Match(finding=Finding.CERTAIN, reason=MatchReason.SOURCE_ID,
                         video_id=facts.source_id, title=facts.title)

    # 2. Bibliothek: gleiche Dauer und gleiche Größe oder gleicher Titel
    if facts.duration:
        candidates = index.same_duration(facts.duration)
        for video in candidates:
            if video.size and video.size == facts.size:
                return _result(Finding.DUPLICATE, MatchReason.SAME_FILE, video)
        best = max(candidates, key=lambda v: fuzz.token_sort_ratio(title, loose_title(v.title)), default=None)
        if best and title and fuzz.token_sort_ratio(title, loose_title(best.title)) >= SAME_TITLE_RATIO:
            return _result(Finding.DUPLICATE, MatchReason.TITLE_DURATION, best)

    # 3. Gleicher Titel: mit gleicher Dauer sicher, ohne Vergleich vermutlich;
    #    Einträge des vermuteten Kanals zuerst
    same_title = [v for v in index.by_title.get(title, ()) if not _contradicts(v.duration, facts.duration)]
    same_title.sort(key=lambda v: v.channel_id != channel_id)
    for video in same_title:
        if _close(video.duration, facts.duration):
            finding = Finding.DUPLICATE if video.in_library else Finding.CERTAIN
            return _result(finding, MatchReason.TITLE_DURATION, video)
    if same_title:
        return _result(Finding.PROBABLE, MatchReason.TITLE, same_title[0])

    # 4. Ähnlicher Titel im vermuteten Kanal
    if channel_id and title:
        scored = [(fuzz.token_sort_ratio(title, known_title), video)
                  for known_title, video in index.by_channel.get(channel_id, ())
                  if not _contradicts(video.duration, facts.duration)]
        ratio, video = max(scored, key=lambda s: s[0], default=(0, None))
        if video and ratio >= SIMILAR_TITLE_RATIO:
            return _result(Finding.PROBABLE, MatchReason.SIMILAR_TITLE, video)

    return Match(finding=Finding.UNKNOWN)
