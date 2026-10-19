"""
TubeVault – Hörbücher und Hörspiele

Hörbücher sind keine Musik (Wunsch 15.10.2026): Sie kommen nie in Musiklisten
oder Zufallsmixe und werden für sich gespielt, streng in ihrer Reihenfolge,
mit Weiterhören an der gemerkten Stelle. Es gibt sie als Dateien der eigenen
Sammlung und als Videos.

Ein Buch ist
  aus Dateien  ein Album (Album-Interpret bzw. Interpret und Albumname) der
               Dateien mit Art Hörbuch (music_files.category), ohne Album ihr Ordner;
               Reihenfolge: CD, Titelnummer, Dateipfad natürlich sortiert
  aus Videos   eine erkannte Reihe ("Teil 3", "Folge 12" ... series_detector)
               der als Hörbuch gekennzeichneten Videos (audiobook_flag), in
               Folgenreihenfolge; ein Video ohne Reihe ist ein Buch für sich.
Der Stand je Buch (welcher Teil, welche Stelle) liegt in audiobook_progress.
"""
import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import music_files, music_library, series_detector
from app.services.music_library import Track

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audiobook_progress (
    book TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,            -- der Teil: Musikdatei oder Video
    position REAL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

FINISHED_REST_S = 30   # weniger Rest im letzten Teil gilt als zu Ende gehört
MIN_VIDEO_PARTS = 2    # ab so vielen nummerierten Teilen ist es eine Reihe


class Book(BaseModel):
    key: str                          # Quelle zum Abspielen: hoerbuch:<key>
    title: str
    author: Optional[str] = None
    kind: str                         # datei | video
    parts: int
    duration: int
    cover_id: Optional[str] = None    # Titel mit Bild
    current_part: Optional[int] = None    # 1-basiert, wo es weitergeht
    position: float = 0
    remaining: int = 0                # Sekunden bis zum Ende
    finished: bool = False
    updated_at: Optional[str] = None


@dataclass
class _Group:
    title: str
    author: Optional[str]
    kind: str
    parts: list[Track]
    cover_id: Optional[str]


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


def _key(basis: str) -> str:
    return hashlib.sha1(basis.casefold().encode("utf-8")).hexdigest()[:12]


def _natural(text: str) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


async def _file_books() -> dict[str, _Group]:
    books: dict[str, tuple[str, Optional[str], list[music_files.FileInfo]]] = {}
    for f in await music_files.all_files(music_files.AUDIOBOOK):
        author = f.album_artist or f.artist
        if f.album:
            key, title = _key(f"{author or ''}|{f.album}"), f.album
        else:
            folder = str(PurePosixPath(f.path).parent)
            key, title = _key(folder), PurePosixPath(folder).name or f.title
        books.setdefault(key, (title, author, []))[2].append(f)
    result = {}
    ctx = await music_library.context()
    for key, (title, author, files) in books.items():
        files.sort(key=lambda f: (f.disc_no or 0, f.track_no or 0, _natural(f.path)))
        result[key] = _Group(title, author, "datei", [music_library.file_track(f, ctx) for f in files],
                             next((f.id for f in files if f.has_cover), None))
    return result


async def _video_books() -> dict[str, _Group]:
    rows = [dict(r) for r in await db.fetch_all(
        f"{music_library.TRACK_SQL} AND COALESCE(v.is_audiobook, 0) = 1 ORDER BY v.upload_date, v.id")]
    if not rows:
        return {}
    by_id = {r["id"]: r for r in rows}
    ctx = await music_library.context()
    result: dict[str, _Group] = {}
    in_series: set[str] = set()
    for series in series_detector.detect(
            [{"id": r["id"], "title": r["title"], "channel_id": r["channel_id"], "channel_name": r["channel_name"],
              "upload_date": r.get("upload_date")} for r in rows], min_episodes=MIN_VIDEO_PARTS):
        ids = [e.video_id for e in sorted(series.episodes, key=lambda e: (e.season or 0, e.number)) if e.video_id in by_id]
        if len(ids) < MIN_VIDEO_PARTS or in_series & set(ids):
            continue
        in_series.update(ids)
        result[_key(f"video|{series.key}")] = _Group(series.name, series.channel_name, "video",
                                                     [music_library.video_track(by_id[i], ctx) for i in ids], ids[0])
    for row in rows:
        if row["id"] not in in_series:
            result[_key(f"video|{row['id']}")] = _Group(row["title"], row["channel_name"], "video",
                                                        [music_library.video_track(row, ctx)], row["id"])
    return result


async def _grouped() -> dict[str, _Group]:
    return {**await _file_books(), **await _video_books()}


async def books() -> list[Book]:
    """Alle Hörbücher, zuletzt gehörte zuerst, dann nach Titel."""
    progress = {r["book"]: r for r in await db.fetch_all("SELECT * FROM audiobook_progress")}
    result = []
    for key, group in (await _grouped()).items():
        durations = [int(p.duration or 0) for p in group.parts]
        book = Book(key=key, title=group.title, author=group.author, kind=group.kind, parts=len(group.parts),
                    duration=sum(durations), cover_id=group.cover_id, remaining=sum(durations))
        saved = progress.get(key)
        index = next((i for i, p in enumerate(group.parts) if saved and p.id == saved["file_id"]), None)
        if index is not None:
            book.current_part, book.position, book.updated_at = index + 1, saved["position"] or 0, saved["updated_at"]
            book.remaining = max(0, int(sum(durations[index:]) - book.position))
            book.finished = index == len(group.parts) - 1 and book.remaining <= FINISHED_REST_S
        result.append(book)
    result.sort(key=lambda b: b.title.casefold())
    result.sort(key=lambda b: b.updated_at or "", reverse=True)   # zuletzt gehörte zuerst, ungehörte danach
    return result


async def parts(key: str) -> tuple[str, list[Track]]:
    """(Titel, Teile in Reihenfolge) eines Buchs; LookupError, wenn es das nicht gibt."""
    group = (await _grouped()).get(key)
    if not group:
        raise LookupError("Hörbuch unbekannt")
    return group.title, group.parts


async def resume_point(key: str) -> tuple[Optional[str], float]:
    """(Teil, Stelle), an der es weitergeht; (None, 0) ohne Stand."""
    row = await db.fetch_one("SELECT file_id, position FROM audiobook_progress WHERE book = ?", (key,))
    return (row["file_id"], row["position"] or 0) if row else (None, 0)


async def save_progress(key: str, part_id: str, position: float) -> None:
    _, items = await parts(key)
    if not any(p.id == part_id for p in items):
        raise LookupError("Teil gehört nicht zu diesem Hörbuch")
    await db.execute(
        """INSERT INTO audiobook_progress (book, file_id, position, updated_at) VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(book) DO UPDATE SET file_id = excluded.file_id, position = excluded.position,
               updated_at = excluded.updated_at""", (key, part_id, max(0.0, position)))


async def reset(key: str) -> None:
    """Von vorn: gemerkten Stand vergessen."""
    await db.execute("DELETE FROM audiobook_progress WHERE book = ?", (key,))
