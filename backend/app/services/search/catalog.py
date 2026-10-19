"""
Kanäle, Playlists und die eigene Musiksammlung.

Kanäle und Playlists sind wenige; sie werden direkt verglichen
(text.prepared_matching, dieselben Wortregeln wie die Indexe). Die
abonnierten Kanäle liegen dafür vorbereitet im Speicher und werden neu
gelesen, sobald sich an ihnen etwas ändert. Kanäle der Bibliothek ohne Abo
kommen aus den Videotreffern (Name im Index getroffen). Die Musiksammlung
hat einen eigenen Volltextindex (search.index.music_fts).
"""
from typing import Optional

from app.database import db
from app.services import music_files, music_library
from app.services.search.models import ChannelHit, MusicHit, PlaylistHit
from app.services.search.query import Query
from app.services.search.text import Prepared, prepare, prepared_matching

_subscriptions: tuple[Optional[tuple], list[tuple[dict, Prepared]]] = (None, [])


async def _subscribed() -> list[tuple[dict, Prepared]]:
    """Abonnierte Kanäle samt vorbereitetem Text; neu gelesen nur nach Änderungen."""
    global _subscriptions
    stamp = tuple(await db.fetch_one(
        """SELECT COUNT(*), MAX(id), SUM(LENGTH(COALESCE(channel_name, '')) + LENGTH(COALESCE(channel_description, ''))
                  + LENGTH(COALESCE(channel_tags, ''))) FROM subscriptions"""))
    if stamp != _subscriptions[0]:
        rows = await db.fetch_all(
            "SELECT channel_id, channel_name, channel_description, channel_tags, language FROM subscriptions")
        _subscriptions = (stamp, [(dict(row), prepare({
            "name": row["channel_name"] or "", "beschreibung": row["channel_description"] or "",
            "schlagwort": row["channel_tags"] or ""})) for row in rows])
    return _subscriptions[1]


async def channels(query: Query, hits_per_channel: dict[str, int], named: dict[str, str]) -> list[ChannelHit]:
    """Abonnierte Kanäle nach Name, Beschreibung und Schlagwörtern, dazu
    Kanäle der Bibliothek, deren Name getroffen wurde (named: Kennung -> Name).
    Name vor Beschreibung, dann die meisten Treffer.
    hits_per_channel: Videotreffer je Kanal (aus den Videos)."""
    if query.empty:
        return []
    found: dict[str, tuple[bool, ChannelHit]] = {}
    for row, prepared in await _subscribed():
        fields = prepared_matching(prepared, query)
        if fields:
            found[row["channel_id"]] = ("name" in fields, ChannelHit(
                channel_id=row["channel_id"], channel_name=row["channel_name"] or row["channel_id"], subscribed=True,
                videos=hits_per_channel.get(row["channel_id"], 0), language=row["language"]))
    for channel_id, name in named.items():
        if channel_id not in found:
            found[channel_id] = (True, ChannelHit(channel_id=channel_id, channel_name=name or channel_id,
                                                  subscribed=False, videos=hits_per_channel.get(channel_id, 0)))
    ranked = sorted(found.values(), key=lambda pair: (not pair[0], -pair[1].videos, pair[1].channel_name.lower()))
    return [hit for _, hit in ranked]


async def playlists(query: Query) -> list[PlaylistHit]:
    """Eigene Playlists nach Name und Beschreibung, Name zuerst."""
    if query.empty:
        return []
    found = []
    for row in await db.fetch_all("SELECT id, name, description, video_count FROM playlists"):
        fields = prepared_matching(prepare({"name": row["name"] or "", "beschreibung": row["description"] or ""}), query)
        if fields:
            found.append(("name" not in fields, PlaylistHit(
                id=row["id"], name=row["name"] or "", description=row["description"],
                video_count=row["video_count"] or 0)))
    return [hit for _, hit in sorted(found, key=lambda pair: (pair[0], pair[1].name.lower()))]


# Spalten von music_fts und wie der Fund heißt (Reihenfolge = Gewicht)
_MUSIC_COLUMNS = (("titel", "title"), ("kuenstler", "artist album_artist"), ("album", "album"),
                  ("genre", "genre"), ("liedtext", "lyrics_text"))


async def music(query: Query) -> list[MusicHit]:
    """Titel der eigenen Sammlung nach Titel, Künstler, Album, Genre und
    Liedtext (nur wenn die Sammlung als Musikquelle gilt). Fund im Titel
    zuerst, dann nach Künstler und Titel."""
    expression = query.full_expression()
    if not expression or await music_library.source_setting() == "videos":
        return []
    rows = await db.fetch_all(
        f"""SELECT m.*, m.rowid AS doc FROM music_fts JOIN music_files m ON m.rowid = music_fts.rowid
            WHERE music_fts MATCH ? AND {music_files.VISIBLE}""", (expression,))
    if not rows:
        return []
    places: dict[int, list[str]] = {row["doc"]: [] for row in rows}
    for label, columns in _MUSIC_COLUMNS:
        for hit in await db.fetch_all("SELECT rowid FROM music_fts WHERE music_fts MATCH ?",
                                      (query.in_columns(columns),)):
            if hit[0] in places:
                places[hit[0]].append(label)
    found = []
    ctx = await music_library.context()
    for row in rows:
        track = music_library.file_track(music_files.info_of(row), ctx)
        labels = places[row["doc"]]           # leer: Wörter auf mehrere Felder verteilt
        found.append(((not labels or labels[0] != "titel", track.artist.lower(), track.title.lower()),
                      MusicHit(track=track, year=row["year"], genre=row["genre"], found=labels)))
    return [hit for _, hit in sorted(found, key=lambda pair: pair[0])]
