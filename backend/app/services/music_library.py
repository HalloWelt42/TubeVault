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

Abgewählte Titel (Minus-Knopf: Dateien music_files.hidden, Videos
music_video_hiding) und ausgeschlossene Alben (music_exclusions) fallen
überall heraus; ein Album ohne sichtbare Titel gibt es dann nicht mehr. Das
Video-Doppel einer ausgeblendeten Datei rückt nicht nach.

Alben der Dateien: gleiches Cover oder gleicher Ordner mit gleichem
Albumnamen, fortgesetzt (music_albums, entschieden 19.10.2026); Videos bilden
ihre Alben aus Interpret und music_album. Welches Album ein Titel hat, steht
allein in Track.album_source; Albenliste, Abspielen und Ausschließen fragen nur
dort. Ein früherer Schlüssel eines Albums führt über music_albums.resolve zum
heutigen.

Interpret und Songtitel: was am Video festgelegt ist (music_artist,
music_title), sonst aus "Interpret - Titel" im Videotitel, sonst der Kanal.
Das dient nur der Anzeige und Gruppierung - ob etwas Musik ist, entscheidet
allein music_flag. Nennt die Angabe mehrere Interpreten ("50 Cent, Nate
Dogg"), zählt der Titel bei jedem (Track.artists, music_artists, entschieden
19.10.2026); angezeigt wird die Angabe, wie sie ist (Track.artist).
"""
import random
import re
from collections import Counter
from typing import Iterable, NamedTuple, Optional

from pydantic import BaseModel

from app.database import db
from app.services import (music_albums, music_artists, music_exclusions, music_files, music_video_hiding,
                          playlist_items, setting_values)
from app.services.lyrics_service import suggest_artist_title
from app.services.music_keys import group_key

MUSIC_SOURCE = "music.source"
MUSIC_LIST = "musik"                 # playlists.source einer in der Musik angelegten Liste
VIDEO = "video"
FILE = "datei"
VARIOUS_ARTISTS = "Verschiedene Interpreten"
COLLAGE = 4                          # so viele Bilder höchstens in der Kachel einer Gruppe

# Zusätze an Kanalnamen von Musikkanälen
_CHANNEL_NOISE = re.compile(r"(?:\s*-\s*Topic|VEVO|\s+Official|\s+Music)$", re.IGNORECASE)
# Zusätze am Ende eines Songtitels
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*(?:official|video|audio|lyric|visualizer|clip|uncensored|mix|remaster)[^\)\]]*[\)\]]\s*$",
    re.IGNORECASE)


class ArtistRef(BaseModel):
    """Ein Genannter eines Titels: der Name, wie er in der Angabe steht, und seine Gruppe."""
    name: str
    source: str                      # artist:<schlüssel>, Quelle zum Abspielen aller seiner Titel


class Track(BaseModel):
    id: str
    title: str
    artist: str                      # die Angabe, wie sie im Tag bzw. am Video steht (so angezeigt)
    artists: list[ArtistRef]         # jeder Genannte (music_artists): der Titel zählt bei jedem
    album: Optional[str] = None
    album_source: Optional[str] = None   # Gruppe des Albums: die eine Wahrheit, wer zu welchem Album gehört
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
    cover_hash: Optional[str] = None # gleiche Prüfsumme, gleiches Bild (Dateien mit Cover)


class Group(BaseModel):
    """Interpret, Album oder Kanal: eine dynamische Wiedergabeliste."""
    key: str                         # Quelle zum Abspielen, z.B. "artist:abba"
    name: str
    subtitle: Optional[str] = None
    count: int
    duration: int
    covers: list[str]                # bis zu vier Titel mit verschiedenen Bildern (Bild über /api/music/cover); eins = ein Bild
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


def video_album(artist: str, album: Optional[str]) -> Optional[str]:
    """Album eines Videos: Interpret und Albumname; ohne Albumnamen keins."""
    return f"album:{group_key(f'{artist}|{album}')}" if album else None


class Context(NamedTuple):
    """Was das Einordnen eines Titels braucht, einmal je Datenstand gerechnet."""
    albums: music_albums.AlbumIndex
    naming: music_artists.Naming


async def context() -> Context:
    return Context(albums=await music_albums.index(), naming=await music_artists.naming())


def artist_refs(artist: str, ctx: Context) -> list[ArtistRef]:
    """Die Genannten einer Angabe mit ihren Gruppen (Namen: music_artists)."""
    return [ArtistRef(name=name, source=f"artist:{group_key(name)}") for name in ctx.naming.names(artist)]


async def excluded_albums(ctx: Context) -> set[str]:
    """Ausgeschlossene Alben unter ihrem heutigen Schlüssel."""
    return {ctx.albums.resolve(source) for source in await music_exclusions.sources()}


TRACK_SELECT = """SELECT v.id, v.title, v.music_artist, v.music_title, v.music_album, v.channel_id, v.channel_name,
                            v.upload_date, v.duration, COALESCE(v.play_count, 0) AS play_count, v.last_played,
                            v.download_date, COALESCE(v.has_lyrics, 0) AS has_lyrics,
                            COALESCE(v.is_music, 0) AS is_music, v.music_hidden_at,
                            EXISTS (SELECT 1 FROM favorites f WHERE f.video_id = v.id) AS favorite
                     FROM videos v WHERE v.status = 'ready'"""
# Jede Musikliste liest ihre Videos hier: abgewählte fallen überall heraus,
# auch aus Hörbüchern und als Musik gespielten Sammlungen
TRACK_SQL = f"{TRACK_SELECT} AND {music_video_hiding.VISIBLE}"


def video_track(row, ctx: Context) -> Track:
    """Ein Video als Titel. Musik heißt "Interpret - Song", alles andere
    behält seinen Videotitel, der Kanal steht als Interpret."""
    if row["is_music"]:
        artist, title = names_of(row)
    else:
        artist, title = clean_channel(row["channel_name"]) or "Unbekannt", row["title"] or row["id"]
    return Track(id=row["id"], title=title, artist=artist, artists=artist_refs(artist, ctx),
                 album=row["music_album"] or None, album_source=video_album(artist, row["music_album"]),
                 channel_id=row["channel_id"], channel_name=row["channel_name"],
                 duration=row["duration"], play_count=row["play_count"], last_played=row["last_played"],
                 added=row["download_date"], favorite=bool(row["favorite"]),
                 has_lyrics=bool(row["has_lyrics"]))


def file_track(f: music_files.FileInfo, ctx: Context) -> Track:
    artist = (f.artist or f.album_artist or "Unbekannt").strip()
    return Track(id=f.id, title=f.title, artist=artist, artists=artist_refs(artist, ctx),
                 album=f.album, album_source=ctx.albums.of(f.id),
                 duration=int(f.duration) if f.duration else None, play_count=f.play_count,
                 last_played=f.last_played, added=f.added_at, favorite=f.favorite, has_lyrics=f.has_lyrics, kind=FILE,
                 codec=f.codec, cover_hash=f.cover_hash)


async def video_tracks() -> list[Track]:
    # Hörbücher und Hörspiele sind keine Musik, auch wenn sie so gekennzeichnet sind
    rows = await db.fetch_all(
        f"{TRACK_SQL} AND v.is_music = 1 AND COALESCE(v.is_audiobook, 0) = 0 ORDER BY v.download_date DESC, v.id")
    ctx = await context()
    return [video_track(row, ctx) for row in rows]


async def source_setting() -> str:
    return await setting_values.get(MUSIC_SOURCE)


async def tracks(source: Optional[str] = None) -> list[Track]:
    """Alle Musiktitel einer Quelle (alle, sammlung, videos), neueste zuerst;
    ohne Angabe die gewählte (music.source)."""
    source = source or await source_setting()
    ctx = await context()
    videos = await video_tracks() if source != "sammlung" else []
    every_file = await music_files.all_files(visible_only=False) if source != "videos" else []
    file_tracks = [(f, file_track(f, ctx)) for f in every_file]
    files = [t for f, t in file_tracks if not f.hidden]
    if videos and every_file:
        # Doppelte Songs: die Datei gilt (bessere Tonqualität) - auch eine
        # ausgeblendete, sonst käme der Song als Video zurück
        have = {(group_key(t.artist), group_key(t.title)) for _, t in file_tracks}
        videos = [t for t in videos if (group_key(t.artist), group_key(t.title)) not in have]
    excluded = await excluded_albums(ctx)
    merged = [t for t in (*videos, *files) if t.album_source not in excluded]
    merged.sort(key=lambda t: t.added or "", reverse=True)
    return merged


async def tracks_of(video_ids: list[str]) -> list[Track]:
    """Beliebige geladene Videos als Titel, in der übergebenen Reihenfolge."""
    if not video_ids:
        return []
    marks = ",".join("?" * len(video_ids))
    ctx = await context()
    by_id = {r["id"]: video_track(r, ctx) for r in await db.fetch_all(f"{TRACK_SQL} AND v.id IN ({marks})", video_ids)}
    return [by_id[i] for i in video_ids if i in by_id]


async def hidden_tracks() -> list[Track]:
    """Abgewählte Titel beider Arten für den Bereich "Ausgeblendet", zuletzt abgewählte zuerst."""
    ctx = await context()
    files = [(f.hidden_at or "", file_track(f, ctx)) for f in await music_files.hidden_files()]
    rows = await db.fetch_all(f"{TRACK_SELECT} AND {music_video_hiding.HIDDEN}")
    videos = [(row["music_hidden_at"] or "", video_track(row, ctx)) for row in rows]
    return [track for _, track in sorted((*files, *videos), key=lambda pair: pair[0], reverse=True)]


def _most_common(names: Iterable[str]) -> str:
    """Schreibweise, die am häufigsten vorkommt (bei Gleichstand die erste)."""
    spellings = Counter(names)
    return max(spellings, key=spellings.get)


def _covers(members: list[Track]) -> list[str]:
    """Bis zu vier Titel mit verschiedenen Bildern für die Collage: Dateien mit
    gleichem Cover zählen einmal, jedes Video hat sein eigenes Bild."""
    seen, chosen = set(), []
    for track in members:
        image = track.cover_hash or track.id
        if image not in seen:
            seen.add(image)
            chosen.append(track.id)
            if len(chosen) == COLLAGE:
                break
    return chosen


def _group(source: str, members: list[Track], names: list[str], subtitle_of=None) -> Group:
    return Group(key=source, name=_most_common(names),
                 subtitle=subtitle_of(members) if subtitle_of else None,
                 count=len(members), duration=sum(t.duration or 0 for t in members),
                 covers=_covers(members), kinds=sorted({t.kind for t in members}))


def _groups(items: list[Track], entries_of, subtitle_of=None) -> list[Group]:
    """Titel zu Gruppen bündeln. entries_of(titel) nennt die Gruppen eines
    Titels als (Quelle, Name in diesem Titel) - einer kann in mehreren stehen."""
    buckets: dict[str, tuple[list[Track], list[str]]] = {}
    for track in items:
        for source, name in entries_of(track):
            members, names = buckets.setdefault(source, ([], []))
            members.append(track)
            names.append(name)
    groups = [_group(source, members, names, subtitle_of) for source, (members, names) in buckets.items()]
    return sorted(groups, key=lambda g: g.name.casefold())


def _album_of(track: Track) -> list[tuple[str, str]]:
    return [(track.album_source, track.album)] if track.album_source else []


def _artists_of(track: Track) -> list[tuple[str, str]]:
    return [(a.source, a.name) for a in track.artists]


def _channel_of(track: Track) -> list[tuple[str, str]]:
    return [(f"channel:{track.channel_id}", track.channel_name or track.channel_id)] if track.channel_id else []


def artist_name(members: list[Track], source: str) -> str:
    """Häufigste Schreibweise eines Interpreten unter den Titeln, die ihn nennen."""
    return _most_common(a.name for t in members for a in t.artists if a.source == source)


def album_subtitle(members: list[Track]) -> str:
    """Der Interpret, den alle Titel nennen, sonst "Verschiedene Interpreten".
    Tragen alle dieselbe Angabe, steht sie da; sonst der gemeinsam Genannte
    (ein Album von 50 Cent bleibt seins, auch mit "50 Cent, Nate Dogg")."""
    shared = set.intersection(*({a.source for a in t.artists} for t in members))
    if not shared:
        return VARIOUS_ARTISTS
    if len({group_key(t.artist) for t in members}) == 1:
        return _most_common(t.artist for t in members)
    return artist_name(members, next(a.source for a in members[0].artists if a.source in shared))


def artists(items: list[Track]) -> list[Group]:
    return _groups(items, _artists_of)


def albums(items: list[Track]) -> list[Group]:
    return _groups(items, _album_of, subtitle_of=album_subtitle)


def channels(items: list[Track]) -> list[Group]:
    return _groups(items, _channel_of)


async def album(source: str) -> Optional[Group]:
    """Ein Album mit Name und Unterzeile wie in der Albenliste, unter seinem
    heutigen Schlüssel (source darf ein früherer sein); None ohne sichtbare Titel."""
    wanted = (await context()).albums.resolve(source)
    members = [t for t in await tracks() if t.album_source == wanted]
    return _group(wanted, members, [t.album for t in members], album_subtitle) if members else None


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
        chosen = [t for t in items if any(a.source == source for a in t.artists)]
        chosen.sort(key=SORTS["title"])
        title = artist_name(chosen, source) if chosen else "Interpret"
    elif kind == "album":
        wanted = (await context()).albums.resolve(source)
        chosen = [t for t in items if t.album_source == wanted]
        title = _most_common(t.album for t in chosen) if chosen else "Album"
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
    ctx = await context()
    found = {t.id: t for t in await tracks_of([i for i in ids if not music_files.is_file_id(i)])}
    found.update({f.id: file_track(f, ctx) for f in await music_files.all_files() if f.id in wanted})
    excluded = await excluded_albums(ctx)
    return {i: t for i, t in found.items() if t.album_source not in excluded}


async def _music_list_rows() -> list:
    """Listen für die Musik: in der Musik angelegte (auch leere) und alle
    übrigen mit mindestens einem Musiktitel; zuletzt angelegte zuerst."""
    with_music = {row["playlist_id"] for row in await db.fetch_all(
        f"""SELECT DISTINCT p.playlist_id FROM playlist_videos p JOIN videos v ON v.id = p.video_id
            WHERE v.is_music = 1 AND v.status = 'ready' AND {music_video_hiding.VISIBLE}
            UNION SELECT DISTINCT playlist_id FROM playlist_files""")}
    return [row for row in await db.fetch_all("SELECT id, name, source FROM playlists ORDER BY created_at DESC, id DESC")
            if row["id"] in with_music or row["source"] == MUSIC_LIST]


async def music_playlist_count() -> int:
    return len(await _music_list_rows())


async def music_playlists() -> list[Group]:
    """Die Listen der Musik (_music_list_rows) als Gruppen. Gezählt wird alles,
    was die Liste spielt (_list_tracks)."""
    shown = await _music_list_rows()
    entries = {row["id"]: await playlist_items.entries(row["id"]) for row in shown}
    by_id = await _list_tracks([i for ids in entries.values() for i in ids])
    groups = []
    for row in shown:
        found = [by_id[i] for i in entries[row["id"]] if i in by_id]
        groups.append(Group(key=f"playlist:{row['id']}", name=row["name"], count=len(found),
                            duration=sum(t.duration or 0 for t in found), covers=_covers(found),
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
        named = {a.source for a in seed.artists}
        rest = [t for t in items if t.id != video_id and
                (named & {a.source for a in t.artists} or (seed.channel_id and t.channel_id == seed.channel_id))]
        random.shuffle(rest)
        chosen += rest[:limit]
    return chosen


async def export_items(source: str) -> tuple[str, list[tuple[str, str]]]:
    """(Titel, [(Kennung, "Interpret - Titel")]) für den Ton-Export einer
    Quelle. Eine Wiedergabeliste gibt alle ihre geladenen Videos und Dateien
    aus, nicht nur die als Musik gekennzeichneten - abgewählte nicht."""
    kind, _, value = source.partition(":")
    if kind == "playlist":
        name = await db.fetch_val("SELECT name FROM playlists WHERE id = ?", (value,))
        if name is None:
            raise ValueError("Wiedergabeliste unbekannt")
        ids = await playlist_items.entries(_list_id(value))
        marks = ",".join("?" * len(ids)) or "''"
        rows = {r["id"]: r for r in await db.fetch_all(
            f"""SELECT v.id, v.title, v.music_artist, v.music_title, v.channel_name, v.is_music
                FROM videos v WHERE v.status = 'ready' AND {music_video_hiding.VISIBLE} AND v.id IN ({marks})""", ids)}
        files = {f.id: f for f in await music_files.all_files(category=None)}

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

