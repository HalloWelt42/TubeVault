"""
TubeVault – Alben der eigenen Sammlung

Welche Musikdateien ein Album sind (entschieden 19.10.2026, "Cover oder Ordner
und Name"): Titel im selben Ordner mit demselben Albumnamen (Groß- und
Kleinschreibung und Leerraum egal) sind ein Album, und Titel mit genau
demselben Cover (cover_hash) sind eins. Das gilt fortgesetzt: hängt A über das
Cover an B und B über Ordner und Namen an C, sind alle drei ein Album. So
bleibt ein Ordner wie "Space Night" mit einem Albumnamen und vielen Covern ein
Album, ein Sampler mit einem Cover über mehrere Ordner (CD 1, CD 2) und
Schreibweisen auch; ein Download-Ordner mit vielen Albumnamen zerfällt in
seine Alben - der Ordner allein verbindet nie. Ohne Albumnamen gehört eine
Datei zu keinem Album. Videos haben ihre eigenen Alben (Interpret und
music_album, music_library).

Ein Cover verbindet nur, wenn es das Cover seiner Gruppe aus Ordner und Namen
ist: mindestens die Hälfte ihrer Titel trägt es. Sonst hinge jeder Sampler,
dessen Titel das Cover ihres Originalalbums tragen, über diese Titel an den
Originalalben - gemessen 19.10.2026 am Bestand: "Timeless Pop Classics",
"Classic Rock Classics", "Violator (Deluxe)" und neun weitere wären ein Album
mit 681 Titeln geworden. So ist jeder Sampler eins, und Alben über mehrere
CD-Ordner mit einem Cover sind es auch (613 Alben, 248 mit einem Titel).

Schlüssel: Jede Verbindung hat einen,
    album:cover:<sha1 der Bildbytes>              gleiches Cover
    album:ordner:<sha1 von Ordner|Albumname>      gleicher Ordner und Name (gekürzt)
und ein Album heißt nach dem kleinsten Schlüssel seiner Verbindungen. Bei
gleichem Bestand ist das immer derselbe, ohne dass etwas gespeichert wird; ein
Album mit Cover heißt nach seinem Cover ("cover" < "ordner"), wie die Alben
seit 19.10.2026 schon hießen, ein Sampler ohne gemeinsames Cover nach Ordner
und Namen. Ändert sich der Bestand so, dass der Schlüssel wechselt, führt
resolve() einen früheren zum heutigen: jede Verbindung und jedes Cover eines
Titels zeigt auf sein Album (ein Cover mehrerer Alben auf das mit dem
kleinsten Schlüssel). Ausschlüsse (music_exclusions) und offene Verweise
gelten so weiter.

Gerechnet wird über alle Musikdateien, auch ausgeblendete (ein ausgeblendeter
Titel trennt kein Album), einmal je Datenstand der Datenbank.
"""
import hashlib
from collections import Counter
from typing import Iterable, Optional

from app.database import db
from app.services import music_files, shared_cache
from app.services.music_keys import group_key

COVER = "album:cover:"
FOLDER = "album:ordner:"
_FOLDER_DIGITS = 20
_CACHE_KEY = "music_albums"
_ROWS_SQL = "SELECT id, path, album, cover_hash FROM music_files WHERE COALESCE(category, ?) = ?"


def folder_of(path: str) -> str:
    """Ordner einer Datei (relativer Pfad): alles vor dem letzten "/", oberste Ebene leer."""
    return path.rpartition("/")[0]


def folder_link(path: str, album: str) -> str:
    """Schlüssel der Gruppe aus Ordner und Albumname einer Datei."""
    digest = hashlib.sha1(f"{folder_of(path)}|{group_key(album)}".encode("utf-8")).hexdigest()
    return f"{FOLDER}{digest[:_FOLDER_DIGITS]}"


class AlbumIndex:
    """Album jeder Musikdatei und wohin jeder Schlüssel heute führt."""

    def __init__(self, album_of: dict[str, str], current: dict[str, str]):
        self._album_of = album_of          # Kennung der Datei -> Schlüssel ihres Albums
        self._current = current            # Schlüssel jeder Verbindung -> Schlüssel des Albums

    def of(self, file_id: str) -> Optional[str]:
        """Schlüssel des Albums einer Datei; None ohne Album (oder keine Musikdatei)."""
        return self._album_of.get(file_id)

    def resolve(self, source: str) -> str:
        """Heutiger Schlüssel des Albums, zu dem source gehört (auch ein früherer);
        was hier unbekannt ist (Alben der Videos), bleibt, wie es ist."""
        return self._current.get(source, source)


def build(entries: Iterable[tuple[str, str, Optional[str], Optional[str]]]) -> AlbumIndex:
    """Alben aus (Kennung, Pfad, Album, cover_hash) je Datei: Gruppen aus
    Ordner und Namen, verbunden über ihr Cover; die kleinste Verbindung ist
    jeweils die Wurzel und damit der Schlüssel."""
    files = [(file_id, folder_link(path, album), cover_hash) for file_id, path, album, cover_hash in entries
             if (album or "").strip()]
    sizes, covers = Counter(), Counter()
    for _, group, cover_hash in files:
        sizes[group] += 1
        if cover_hash:
            covers[group, cover_hash] += 1

    parent: dict[str, str] = {}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for _, group, cover_hash in files:
        parent.setdefault(group, group)
        if cover_hash and covers[group, cover_hash] * 2 >= sizes[group]:   # das Cover der Gruppe
            cover = f"{COVER}{cover_hash}"
            parent.setdefault(cover, cover)
            low, high = sorted((root(group), root(cover)))
            parent[high] = low
    current = {key: root(key) for key in parent}
    album_of = {file_id: current[group] for file_id, group, _ in files}
    # Jedes Cover eines Titels führt zu seinem Album, auch wenn es nicht verbindet
    for file_id, _, cover_hash in sorted(files, key=lambda f: album_of[f[0]]):
        if cover_hash:
            current.setdefault(f"{COVER}{cover_hash}", album_of[file_id])
    return AlbumIndex(album_of, current)


async def index() -> AlbumIndex:
    """Alben aller Musikdateien, einmal je Datenstand gerechnet."""
    return await shared_cache.for_version(_CACHE_KEY, await db.data_version(), _load)


async def _load() -> AlbumIndex:
    rows = await db.fetch_all(_ROWS_SQL, (music_files.MUSIC, music_files.MUSIC))
    return build((row["id"], row["path"], row["album"], row["cover_hash"]) for row in rows)
