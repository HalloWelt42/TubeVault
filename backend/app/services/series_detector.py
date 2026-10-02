"""
TubeVault – Serien erkennen v1.0.0

Findet in den Titeln geladener Videos nummerierte Folgen und fasst sie zu
Serien zusammen - getrennt je Kanal und je Serie, auch wenn ein Kanal
mehrere Serien nebeneinander veröffentlicht. Aus einer erkannten Serie wird
auf Wunsch eine Playlist in Folgenreihenfolge.

Vorgehen (rein regelbasiert, ohne KI):
  1. Im Titel Folgenkennzeichen suchen: "Folge 12", "Teil 3 von 5", "#8",
     "S02E22", "mmM#167", "Episode 4" ...
  2. Der Serienname ist der Text VOR dem Kennzeichen. Tragen mehrere Videos
     eines Kanals denselben Text davor, ist das die Serie.
  3. Steht vor dem Kennzeichen noch das Thema der Folge ("Serie - Thema -
     Folge 75"), ist der Text je Folge verschieden. Dann zählt der erste
     Abschnitt ("Serie").
  4. Ein Titel kann zu zwei Serien gehören ("... Teil 10 | mmM#167").

Eine Serie braucht mindestens MIN_EPISODES Folgen mit verschiedenen Nummern.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Optional

from pydantic import BaseModel

from app.database import db

MIN_EPISODES = 3
_SEPARATORS = re.compile(r"\s+[-–—|:]\s+|:\s+|\s+\|\s*|\s*\|\s+")

# (Name, Muster). Gruppen: season (optional), num. Reihenfolge = Vorrang.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("staffel", re.compile(r"\bS(?P<season>\d{1,2})\s?E(?P<num>\d{1,3})\b", re.IGNORECASE)),
    ("kuerzel", re.compile(r"(?<![\w#])(?P<code>[A-Za-z][A-Za-z0-9]{1,7})#(?P<num>\d{1,4})\b")),
    ("wort", re.compile(
        r"\b(?:Folge|Teil|Episode|Ep\.?|Part|Kapitel|Chapter|Lektion|Lesson|Tag|Day|Vorlesung|Nr\.?)"
        r"\s*(?P<num>\d{1,4})\b(?:\s*(?:von|of|/)\s*\d{1,4})?", re.IGNORECASE)),
    ("raute", re.compile(r"(?<!\w)#\s?(?P<num>\d{1,4})\b")),
    ("bruch", re.compile(r"[\(\[]\s*(?P<num>\d{1,3})\s*(?:/|von|of)\s*\d{1,3}\s*[\)\]]", re.IGNORECASE)),
]


class Episode(BaseModel):
    video_id: str
    title: str
    number: int
    season: Optional[int] = None


class Series(BaseModel):
    key: str                     # stabil: "<channel_id>|<Art>|<normierter Name>"
    name: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    episodes: list[Episode]
    first: int
    last: int
    missing: list[int]           # Nummern, die in der Reihe fehlen
    playlist_id: Optional[int] = None   # schon als Playlist angelegt?


class _Match(BaseModel):
    kind: str
    number: int
    season: Optional[int] = None
    before: str
    code: Optional[str] = None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _clean_name(text: str) -> str:
    """Trennzeichen und Klammerreste am Rand entfernen."""
    return text.strip(" \t-–—|:,.([")


def find_matches(title: str) -> list[_Match]:
    """Alle Folgenkennzeichen eines Titels (höchstens eines je Art)."""
    matches = []
    for kind, pattern in _PATTERNS:
        m = pattern.search(title)
        if not m:
            continue
        groups = m.groupdict()
        matches.append(_Match(
            kind=kind, number=int(groups["num"]),
            season=int(groups["season"]) if groups.get("season") else None,
            before=_clean_name(title[:m.start()]), code=groups.get("code")))
    # "Teil 2 | #02": die Raute wiederholt nur die Nummer des Wort-Kennzeichens
    words = [m for m in matches if m.kind == "wort"]
    if words:
        matches = [m for m in matches if not (m.kind == "raute" and m.number == words[0].number)]
    return matches


def _candidate_names(match: _Match, channel_name: str) -> list[str]:
    """Mögliche Seriennamen, vom genauesten zum allgemeinsten."""
    if match.kind == "kuerzel":
        return [match.code]
    names = []
    if match.before:
        names.append(match.before)
        first = _clean_name(_SEPARATORS.split(match.before)[0])
        if first and first != match.before:
            names.append(first)
    else:
        names.append(channel_name or "Ohne Kanal")
    if match.season is not None:
        names = [f"{name} Staffel {match.season}" for name in names]
    return names


def detect(videos: list[dict], min_episodes: int = MIN_EPISODES) -> list[Series]:
    """Serien aus Videozeilen (id, title, channel_id, channel_name, upload_date)."""
    # 1. Je Video und Kennzeichen die möglichen Zuordnungen sammeln
    groups: dict[tuple, dict[str, dict]] = defaultdict(dict)   # (channel, kind, name) → video_id → Eintrag
    display: dict[tuple, Counter] = defaultdict(Counter)
    options: dict[tuple[str, str], list[tuple]] = {}            # (video_id, kind) → Gruppen, genaueste zuerst

    for video in videos:
        title = video.get("title") or ""
        for match in find_matches(title):
            keys = []
            for name in _candidate_names(match, video.get("channel_name") or ""):
                normalized = _normalize(name)
                if len(normalized) < 2:
                    continue
                key = (video.get("channel_id") or "", match.kind, normalized)
                groups[key][video["id"]] = {"video": video, "match": match}
                display[key][name] += 1
                keys.append(key)
            if keys:
                options[(video["id"], match.kind)] = keys

    def distinct_numbers(key) -> int:
        return len({(e["match"].season, e["match"].number) for e in groups[key].values()})

    # 2. Jedes Video landet je Kennzeichen in der genauesten Gruppe, die gross genug ist
    chosen: dict[tuple, list[dict]] = defaultdict(list)
    for (video_id, _kind), keys in options.items():
        for key in keys:
            if distinct_numbers(key) >= min_episodes:
                chosen[key].append(groups[key][video_id])
                break

    series = []
    for key, entries in chosen.items():
        numbers = {(e["match"].season, e["match"].number) for e in entries}
        if len(numbers) < min_episodes:
            continue
        entries.sort(key=lambda e: (e["match"].season or 0, e["match"].number,
                                    e["video"].get("upload_date") or ""))
        channel_id, kind, normalized = key
        plain = sorted({e["match"].number for e in entries})
        missing = [] if any(e["match"].season for e in entries) else [
            n for n in range(plain[0], plain[-1] + 1) if n not in set(plain)]
        series.append(Series(
            key=f"{channel_id}|{kind}|{normalized}",
            name=display[key].most_common(1)[0][0],
            channel_id=channel_id or None,
            channel_name=entries[0]["video"].get("channel_name"),
            episodes=[Episode(video_id=e["video"]["id"], title=e["video"]["title"],
                              number=e["match"].number, season=e["match"].season) for e in entries],
            first=plain[0], last=plain[-1],
            missing=missing[:200],
        ))
    series.sort(key=lambda s: (-len(s.episodes), s.name.casefold()))
    return series


# ─── Datenbank ────────────────────────────────────────────────────────

SOURCE = "series"


async def proposals(min_episodes: int = MIN_EPISODES, channel_id: str | None = None) -> list[Series]:
    """Erkannte Serien über alle geladenen Videos (Bibliothek und Archiv)."""
    where, params = "status = 'ready'", []
    if channel_id:
        where += " AND channel_id = ?"
        params.append(channel_id)
    rows = await db.fetch_all(
        f"SELECT id, title, channel_id, channel_name, upload_date FROM videos WHERE {where}", params)
    found = detect([dict(r) for r in rows], min_episodes)
    existing = {r["source_id"]: r["id"] for r in await db.fetch_all(
        "SELECT id, source_id FROM playlists WHERE source = ?", (SOURCE,))}
    for series in found:
        series.playlist_id = existing.get(series.key)
    return found


async def create_playlist(key: str, min_episodes: int = MIN_EPISODES) -> dict:
    """Serie als Playlist anlegen oder eine vorhandene auf Stand bringen
    (neue Folgen einsortieren). Reihenfolge = Folgennummer."""
    channel_id = key.split("|", 1)[0] or None
    series = next((s for s in await proposals(min_episodes, channel_id) if s.key == key), None)
    if not series:
        raise ValueError("Serie nicht gefunden (Titel geändert oder zu wenige Folgen)")
    name = f"{series.name} ({series.channel_name})" if series.channel_name else series.name
    video_ids = [e.video_id for e in series.episodes]
    playlist_id = await save_playlist(name, video_ids, source=SOURCE, source_id=key,
                                      channel_id=series.channel_id,
                                      description=f"Folgen {series.first} bis {series.last}, automatisch erkannt")
    return {"playlist_id": playlist_id, "name": name, "video_count": len(video_ids)}


async def save_playlist(name: str, video_ids: list[str], *, source: str = "manual",
                        source_id: str | None = None, channel_id: str | None = None,
                        description: str | None = None) -> int:
    """Playlist mit genau dieser Videoreihenfolge anlegen bzw. (bei gleicher
    source_id) ersetzen. Von Hand hinzugefügte Videos einer Serien-Playlist
    bleiben am Ende erhalten."""
    video_ids = list(dict.fromkeys(video_ids))
    existing = await db.fetch_one(
        "SELECT id FROM playlists WHERE source = ? AND source_id = ?", (source, source_id)
    ) if source_id else None
    if existing:
        playlist_id = existing["id"]
        kept = [r["video_id"] for r in await db.fetch_all(
            "SELECT video_id FROM playlist_videos WHERE playlist_id = ? ORDER BY position", (playlist_id,))
            if r["video_id"] not in set(video_ids)]
        await db.execute("DELETE FROM playlist_videos WHERE playlist_id = ?", (playlist_id,))
        video_ids = video_ids + kept
        await db.execute(
            "UPDATE playlists SET name = ?, description = ? WHERE id = ?", (name, description, playlist_id))
    else:
        cursor = await db.execute(
            """INSERT INTO playlists (name, description, source, source_id, channel_id, visibility)
               VALUES (?, ?, ?, ?, ?, 'global')""", (name, description, source, source_id, channel_id))
        playlist_id = cursor.lastrowid
    for position, video_id in enumerate(video_ids):
        await db.execute(
            "INSERT OR IGNORE INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
            (playlist_id, video_id, position))
    await db.execute("UPDATE playlists SET video_count = ? WHERE id = ?", (len(video_ids), playlist_id))
    return playlist_id
