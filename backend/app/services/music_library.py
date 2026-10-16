"""
TubeVault – Musiksammlung

Ordnet die Videos, die als Musik gekennzeichnet sind (music_flag), und die
eigenen Musikdateien (music_files, FLAC usw.) wie eine Musiksammlung:
Titel, Interpreten, Alben, Musikkanäle - und macht aus jeder Gruppe eine
dynamische Wiedergabeliste ("alle Titel von ABBA", "alles aus dem Kanal",
"Lieblingssongs", "ähnliche Titel"), wahlweise zufällig.

Welche Quellen gelten, legt die Einstellung music.source fest (alle,
sammlung = nur Dateien, videos). Gibt es einen Song als Datei und als Video,
gilt bei "alle" die Datei (bessere Tonqualität).

Ausgeblendete Dateien und ausgeschlossene Alben (music_exclusions) fallen
überall heraus; ein Album ohne sichtbare Titel gibt es dann nicht mehr. Ihr
Video-Doppel rückt nicht nach.

Interpret und Songtitel: was am Video festgelegt ist (music_artist,
music_title), sonst aus "Interpret - Titel" im Videotitel, sonst der Kanal.
Das dient nur der Anzeige und Gruppierung - ob etwas Musik ist, entscheidet
allein music_flag.
"""
import random
import re
from collections import defaultdict
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import music_exclusions, music_files, playlist_items, setting_values
from app.services.lyrics_service import suggest_artist_title

MUSIC_SOURCE = "music.source"
MUSIC_LIST = "musik"                 # playlists.source einer in der Musik angelegten Liste
VIDEO = "video"
FILE = "datei"

# Zusätze an Kanalnamen von Musikkanälen
_CHANNEL_NOISE = re.compile(r"(?:\s*-\s*Topic|VEVO|\s+Official|\s+Music)$", re.IGNORECASE)
# Zusätze am Ende eines Songtitels
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*(?:official|video|audio|lyric|visualizer|clip|uncensored|mix|remaster)[^\)\]]*[\)\]]\s*$",
    re.IGNORECASE)


class Track(BaseModel):
    id: str
    title: str
    artist: str
    artist_source: str               # Quelle zum Abspielen aller Titel des Interpreten
    album: Optional[str] = None
    album_source: Optional[str] = None   # Gruppe des Albums (z.B. zum Ausschließen)
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    play_count: int = 0
    last_played: Optional[str] = None
    added: Optional[str] = None
    favorite: bool = False
    has_lyrics: bool = False
    kind: str = VIDEO                # video | datei (music_files)
    codec: Optional[str] = None      # Format der Datei (FLAC, MP3 ...); Videos ohne


class Group(BaseModel):
    """Interpret, Album oder Kanal: eine dynamische Wiedergabeliste."""
    key: str                         # Quelle zum Abspielen, z.B. "artist:abba"
    name: str
    subtitle: Optional[str] = None
    count: int
    duration: int
    covers: list[str]                # bis zu vier Titel-Kennungen für die Collage (Bild über /api/music/cover)
    kinds: list[str] = []            # woher die Titel kommen: datei, video


class PlayList(BaseModel):
    source: str
    title: str
    tracks: list[Track]
    start_index: int = 0             # hier beginnen (Hörbücher: der gemerkte Teil)
    start_at: float = 0              # an dieser Stelle in Sekunden


def clean_channel(name: Optional[str]) -> str:
    return _CHANNEL_NOISE.sub("", (name or "").strip()).strip() or (name or "")


def names_of(row) -> tuple[str, str]:
    """(Interpret, Songtitel) eines Musikvideos für Anzeige und Gruppierung."""
    artist, title = row["music_artist"], row["music_title"]
    if not (artist and title):
        guess = suggest_artist_title(row["title"] or "")
        artist = artist or guess["artist"]
        title = title or guess["song_title"]
    artist = artist or clean_channel(row["channel_name"]) or "Unbekannt"
    title = _TITLE_NOISE.sub("", title or row["title"] or row["id"]).strip() or row["title"]
    return artist.strip(), title.strip()


def group_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.casefold()).strip()


def album_source(artist: str, album: Optional[str]) -> Optional[str]:
    return f"album:{group_key(f'{artist}|{album}')}" if album else None


TRACK_SQL = """SELECT v.id, v.title, v.music_artist, v.music_title, v.music_album, v.channel_id, v.channel_name, v.upload_date,
                         v.duration, COALESCE(v.play_count, 0) AS play_count, v.last_played, v.download_date,
                         COALESCE(v.has_lyrics, 0) AS has_lyrics, COALESCE(v.is_music, 0) AS is_music,
                         EXISTS (SELECT 1 FROM favorites f WHERE f.video_id = v.id) AS favorite
                  FROM videos v WHERE v.status = 'ready'"""


def video_track(row) -> Track:
    """Ein Video als Titel. Musik heißt "Interpret - Song", alles andere
    behält seinen Videotitel, der Kanal steht als Interpret."""
    if row["is_music"]:
        artist, title = names_of(row)
    else:
        artist, title = clean_channel(row["channel_name"]) or "Unbekannt", row["title"] or row["id"]
    return Track(id=row["id"], title=title, artist=artist, artist_source=f"artist:{group_key(artist)}",
                 album=row["music_album"] or None, album_source=album_source(artist, row["music_album"]),
                 channel_id=row["channel_id"], channel_name=row["channel_name"],
                 duration=row["duration"], play_count=row["play_count"], last_played=row["last_played"],
                 added=row["download_date"], favorite=bool(row["favorite"]),
                 has_lyrics=bool(row["has_lyrics"]))


def file_track(f: music_files.FileInfo) -> Track:
    artist = (f.artist or f.album_artist or "Unbekannt").strip()
    return Track(id=f.id, title=f.title, artist=artist, artist_source=f"artist:{group_key(artist)}",
                 album=f.album, album_source=album_source(artist, f.album), duration=int(f.duration) if f.duration else None, play_count=f.play_count,
                 last_played=f.last_played, added=f.added_at, favorite=f.favorite, has_lyrics=f.has_lyrics, kind=FILE,
                 codec=f.codec)


async def video_tracks() -> list[Track]:
    # Hörbücher und Hörspiele sind keine Musik, auch wenn sie so gekennzeichnet sind
    rows = await db.fetch_all(
        f"{TRACK_SQL} AND v.is_music = 1 AND COALESCE(v.is_audiobook, 0) = 0 ORDER BY v.download_date DESC, v.id")
    return [video_track(row) for row in rows]


async def source_setting() -> str:
    return await setting_values.get(MUSIC_SOURCE)


async def tracks(source: Optional[str] = None) -> list[Track]:
    """Alle Musiktitel einer Quelle (alle, sammlung, videos), neueste zuerst;
    ohne Angabe die gewählte (music.source)."""
    source = source or await source_setting()
    videos = await video_tracks() if source != "sammlung" else []
    every_file = await music_files.all_files(visible_only=False) if source != "videos" else []
    files = [file_track(f) for f in every_file if not f.hidden]
    if videos and every_file:
        # Doppelte Songs: die Datei gilt (bessere Tonqualität) - auch eine
        # ausgeblendete, sonst käme der Song als Video zurück
        have = {(group_key(t.artist), group_key(t.title)) for t in map(file_track, every_file)}
        videos = [t for t in videos if (group_key(t.artist), group_key(t.title)) not in have]
    excluded = await music_exclusions.sources()
    merged = [t for t in (*videos, *files) if t.album_source not in excluded]
    merged.sort(key=lambda t: t.added or "", reverse=True)
    return merged


async def tracks_of(video_ids: list[str]) -> list[Track]:
    """Beliebige geladene Videos als Titel, in der übergebenen Reihenfolge."""
    if not video_ids:
        return []
    marks = ",".join("?" * len(video_ids))
    by_id = {r["id"]: video_track(r) for r in await db.fetch_all(f"{TRACK_SQL} AND v.id IN ({marks})", video_ids)}
    return [by_id[i] for i in video_ids if i in by_id]


def _groups(items: list[Track], kind: str, key_of, name_of, subtitle_of=None) -> list[Group]:
    buckets: dict[str, list[Track]] = defaultdict(list)
    for track in items:
        key = key_of(track)
        if key:
            buckets[key].append(track)
    groups = []
    for key, members in buckets.items():
        # Schreibweise, die am häufigsten vorkommt
        spellings = defaultdict(int)
        for track in members:
            spellings[name_of(track)] += 1
        name = max(spellings, key=spellings.get)
        groups.append(Group(key=f"{kind}:{key}", name=name,
                            subtitle=subtitle_of(members) if subtitle_of else None,
                            count=len(members), duration=sum(t.duration or 0 for t in members),
                            covers=[t.id for t in members[:4]], kinds=sorted({t.kind for t in members})))
    return sorted(groups, key=lambda g: g.name.casefold())


def artists(items: list[Track]) -> list[Group]:
    return _groups(items, "artist", lambda t: group_key(t.artist), lambda t: t.artist)


def albums(items: list[Track]) -> list[Group]:
    return _groups(items, "album", lambda t: group_key(f"{t.artist}|{t.album}") if t.album else None,
                   lambda t: t.album, subtitle_of=lambda members: members[0].artist)


def channels(items: list[Track]) -> list[Group]:
    return _groups(items, "channel", lambda t: t.channel_id, lambda t: t.channel_name or t.channel_id)


SORTS = {
    "added": lambda t: t.added or "",
    "title": lambda t: t.title.casefold(),
    "artist": lambda t: (t.artist.casefold(), t.title.casefold()),
    "plays": lambda t: t.play_count,
    "duration": lambda t: t.duration or 0,
    "last_played": lambda t: t.last_played or "",
}
DESCENDING = {"added", "plays", "last_played"}


def search(items: list[Track], query: str) -> list[Track]:
    words = query.casefold().split()
    return [t for t in items
            if all(w in f"{t.title} {t.artist} {t.album or ''} {t.channel_name or ''}".casefold() for w in words)]


# ─── Dynamische Wiedergabelisten ──────────────────────────────────────

SOURCE_TITLES = {"all": "Alle Titel", "favorites": "Lieblingssongs", "often": "Oft gehört",
                 "new": "Neu in der Sammlung", "recent": "Zuletzt gehört", "forgotten": "Lange nicht gehört"}


async def play_list(source: str, shuffle: bool = False, start: Optional[str] = None) -> PlayList:
    """Titel einer Quelle in Abspielreihenfolge. start: dieser Titel zuerst
    (beim Zufall), bzw. die Liste beginnt dort (ohne Zufall).
    sammlung:<Quelle> spielt eine Favoritenliste oder Playlist ganz als Ton,
    auch Videos, die keine Musik sind (collections)."""
    kind, _, value = source.partition(":")
    title = SOURCE_TITLES.get(kind, "Musik")
    if kind == "hoerbuch":
        return await _audiobook(source, value, start)
    if kind == "playlist":
        ids = await playlist_items.entries(_list_id(value))
        by_id = await _list_tracks(ids)
        title = await db.fetch_val("SELECT name FROM playlists WHERE id = ?", (value,)) or "Wiedergabeliste"
        return _arranged(source, title, [by_id[i] for i in ids if i in by_id], shuffle, start)
    if kind == "sammlung":
        from app.services import collections
        collection = await collections.load(value)
        items = await tracks_of([item.id for item in collection.items if item.loaded])
        return _arranged(source, collection.title, items, shuffle, start)
    items = await tracks()
    if kind == "all":
        chosen = sorted(items, key=SORTS["artist"])
    elif kind == "artist":
        chosen = [t for t in items if group_key(t.artist) == value]
        chosen.sort(key=SORTS["title"])
        title = chosen[0].artist if chosen else "Interpret"
    elif kind == "album":
        chosen = [t for t in items if t.album and group_key(f"{t.artist}|{t.album}") == value]
        title = chosen[0].album if chosen else "Album"
    elif kind == "channel":
        chosen = [t for t in items if t.channel_id == value]
        title = chosen[0].channel_name if chosen else "Kanal"
    elif kind == "favorites":
        chosen = [t for t in items if t.favorite]
    elif kind == "often":
        chosen = sorted((t for t in items if t.play_count), key=SORTS["plays"], reverse=True)
    elif kind == "new":
        chosen = items[:200]
    elif kind == "recent":
        chosen = sorted((t for t in items if t.last_played), key=SORTS["last_played"], reverse=True)[:200]
    elif kind == "forgotten":
        chosen = sorted(items, key=lambda t: t.last_played or "")[:200]
    elif kind == "similar":
        chosen = await _similar(items, value)
        seed = next((t for t in items if t.id == value), None)
        title = f"Ähnlich wie {seed.title}" if seed else "Ähnliche Titel"
    else:
        raise ValueError("Unbekannte Quelle")
    return _arranged(source, title, chosen, shuffle, start)


def _list_id(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError("Unbekannte Wiedergabeliste")


# ─── Wiedergabelisten der Musik ───────────────────────────────────────

async def _list_tracks(ids: list[str]) -> dict[str, Track]:
    """Titel einer Wiedergabeliste, gleich welche Quelle gewählt ist: eine Liste
    spielt, was in ihr steht - geladene Videos (auch ohne Musik-Kennzeichen)
    und sichtbare Dateien. Ausgeschlossene Alben bleiben auch hier draußen."""
    wanted = set(ids)
    found = {t.id: t for t in await tracks_of([i for i in ids if not music_files.is_file_id(i)])}
    found.update({f.id: file_track(f) for f in await music_files.all_files() if f.id in wanted})
    excluded = await music_exclusions.sources()
    return {i: t for i, t in found.items() if t.album_source not in excluded}


async def music_playlists() -> list[Group]:
    """Listen für die Musik: in der Musik angelegte (auch leere) und alle
    übrigen mit mindestens einem Musiktitel; zuletzt angelegte zuerst. Gezählt
    wird alles, was die Liste spielt (_list_tracks)."""
    with_music = {row["playlist_id"] for row in await db.fetch_all(
        """SELECT DISTINCT p.playlist_id FROM playlist_videos p JOIN videos v ON v.id = p.video_id
           WHERE v.is_music = 1 AND v.status = 'ready'
           UNION SELECT DISTINCT playlist_id FROM playlist_files""")}
    shown = [row for row in await db.fetch_all("SELECT id, name, source FROM playlists ORDER BY created_at DESC, id DESC")
             if row["id"] in with_music or row["source"] == MUSIC_LIST]
    entries = {row["id"]: await playlist_items.entries(row["id"]) for row in shown}
    by_id = await _list_tracks([i for ids in entries.values() for i in ids])
    groups = []
    for row in shown:
        found = [by_id[i] for i in entries[row["id"]] if i in by_id]
        groups.append(Group(key=f"playlist:{row['id']}", name=row["name"], count=len(found),
                            duration=sum(t.duration or 0 for t in found), covers=[t.id for t in found[:4]],
                            kinds=sorted({t.kind for t in found})))
    return groups


async def create_music_playlist(name: str) -> int:
    cursor = await db.execute("INSERT INTO playlists (name, source) VALUES (?, ?)", (name, MUSIC_LIST))
    return cursor.lastrowid


async def _audiobook(source: str, key: str, start: Optional[str]) -> PlayList:
    """Ein Hörbuch in fester Reihenfolge (nie zufällig), ab dem gemerkten Teil
    und der gemerkten Stelle - oder ab einem gewählten Teil von vorn."""
    from app.services import audiobooks
    title, items = await audiobooks.parts(key)
    file_id, position = await audiobooks.resume_point(key)
    if start:
        file_id, position = start, 0
    index = next((i for i, t in enumerate(items) if t.id == file_id), 0)
    return PlayList(source=source, title=title, tracks=items, start_index=index,
                    start_at=position)


def _arranged(source: str, title: str, chosen: list[Track], shuffle: bool, start: Optional[str]) -> PlayList:
    if shuffle:
        chosen = list(chosen)
        random.shuffle(chosen)
        if start:
            chosen.sort(key=lambda t: t.id != start)
    elif start and any(t.id == start for t in chosen):
        index = next(i for i, t in enumerate(chosen) if t.id == start)
        chosen = chosen[index:] + chosen[:index]
    return PlayList(source=source, title=title, tracks=chosen)


async def _similar(items: list[Track], video_id: str, limit: int = 50) -> list[Track]:
    """Inhaltlich ähnliche Titel (Bedeutungssuche); ohne KI: derselbe
    Interpret und derselbe Kanal."""
    from app.services import semantic_index
    by_id = {t.id: t for t in items}
    ranked = await semantic_index.similar_to(video_id, list(by_id), limit) or []
    seed = by_id.get(video_id)
    chosen = [seed] if seed else []
    chosen += [by_id[i] for i in ranked if i != video_id and i in by_id]
    if len(chosen) < 2 and seed:
        rest = [t for t in items if t.id != video_id and
                (group_key(t.artist) == group_key(seed.artist) or t.channel_id == seed.channel_id)]
        random.shuffle(rest)
        chosen += rest[:limit]
    return chosen


async def export_items(source: str) -> tuple[str, list[tuple[str, str]]]:
    """(Titel, [(Kennung, "Interpret - Titel")]) für den Ton-Export einer
    Quelle. Eine Wiedergabeliste gibt alle ihre geladenen Videos und Dateien
    aus, nicht nur die als Musik gekennzeichneten."""
    kind, _, value = source.partition(":")
    if kind == "playlist":
        name = await db.fetch_val("SELECT name FROM playlists WHERE id = ?", (value,))
        if name is None:
            raise ValueError("Wiedergabeliste unbekannt")
        ids = await playlist_items.entries(_list_id(value))
        marks = ",".join("?" * len(ids)) or "''"
        rows = {r["id"]: r for r in await db.fetch_all(
            f"""SELECT id, title, music_artist, music_title, channel_name, is_music
                FROM videos WHERE status = 'ready' AND id IN ({marks})""", ids)}
        files = {f.id: f for f in await music_files.all_files(category=None, visible_only=False)}

        def label(item_id: str) -> Optional[str]:
            if item_id in files:
                f = files[item_id]
                return f"{f.artist} - {f.title}" if f.artist else f.title
            row = rows.get(item_id)
            if not row:
                return None
            # Musik als "Interpret - Titel", alles andere unter seinem Videotitel
            return " - ".join(names_of(row)) if row["is_music"] else (row["title"] or row["id"])
        return name, [(i, label(i)) for i in ids if label(i)]
    playlist = await play_list(source)
    return playlist.title, [(t.id, f"{t.artist} - {t.title}") for t in playlist.tracks]

