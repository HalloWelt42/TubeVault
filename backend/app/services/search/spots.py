"""
Fundstellen mit Zeit: Gesagtes (Abschnitte der Transkripte und Untertitel,
transcript_fts) und Kapitel (chapters_fts). Angezeigt werden die Stellen je
Video in zeitlicher Folge.

Das Gesagte umfasst Hunderttausende Abschnitte. Eine Relevanzrechnung über
alle Treffer eines häufigen Wortes ("die") würde die eine Datenbankverbindung
lange blockieren; deshalb zählen höchstens MAX_SPOTS Stellen, ohne Rechnung
gelesen, und die Videos mit den meisten Stellen stehen vorn. Sind es mehr,
meldet der Bereich das (capped), statt still abzuschneiden.
"""
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services.search.models import Spot, VideoSpots
from app.services.search.query import Query
from app.services.search.text import excerpt, first_hit

# So viele Stellen gehen höchstens in eine Suche ein (die besten nach Relevanz)
MAX_SPOTS = 3000
# So viele Stellen stehen an einem Treffer in der Liste
SPOTS_PER_VIDEO = 3
# Vorschau eines Videos: so viele Stellen je Art
PREVIEW_SPOTS = 30
EXCERPT_CHARS = 220


class SpotHits(BaseModel):
    order: list[str] = []                     # Videos, beste zuerst
    spots: dict[str, list[Spot]] = {}         # die ersten Stellen je Video, zeitlich geordnet
    counts: dict[str, int] = {}               # gezählte Stellen je Video
    capped: bool = False                      # es gibt mehr Stellen als gezählt


def _group(rows, make, *, by_count: bool = False) -> SpotHits:
    """Stellen je Video bündeln; Reihenfolge wie geliefert oder (by_count)
    nach der Zahl der Stellen."""
    result = SpotHits()
    for row in rows:
        video_id = row["video_id"]
        if video_id not in result.counts:
            result.order.append(video_id)
            result.counts[video_id] = 0
            result.spots[video_id] = []
        result.counts[video_id] += 1
        if len(result.spots[video_id]) < SPOTS_PER_VIDEO:
            result.spots[video_id].append(make(row))
    for spots in result.spots.values():
        spots.sort(key=lambda spot: spot.start)
    if by_count:
        first = {video_id: index for index, video_id in enumerate(result.order)}
        result.order.sort(key=lambda video_id: (-result.counts[video_id], first[video_id]))
    return result


def _spoken_spot(query: Query):
    def make(row) -> Spot:
        return Spot(kind="gesagt", start=row["start"], text=excerpt(row["text"], query.terms, EXCERPT_CHARS),
                    origin=row["kind"])
    return make


def _chapter_spot(row) -> Spot:
    return Spot(kind="kapitel", start=row["start_time"] or 0, text=row["title"] or "")


_SPOKEN_SQL = """SELECT c.video_id, c.start, c.text, t.kind
    FROM transcript_fts JOIN transcript_chunks c ON c.id = transcript_fts.rowid
    LEFT JOIN transcripts t ON t.video_id = c.video_id
    WHERE transcript_fts MATCH ?"""
_CHAPTER_SQL = """SELECT c.video_id, c.start_time, c.title
    FROM chapters_fts JOIN chapters c ON c.id = chapters_fts.rowid
    WHERE chapters_fts MATCH ?"""


async def spoken(query: Query) -> SpotHits:
    expression = query.full_expression()
    if not expression:
        return SpotHits()
    rows = await db.fetch_all(
        """SELECT c.video_id, c.start, c.text, t.kind
           FROM (SELECT rowid AS id FROM transcript_fts WHERE transcript_fts MATCH ? LIMIT ?) m
           JOIN transcript_chunks c ON c.id = m.id
           LEFT JOIN transcripts t ON t.video_id = c.video_id""", (expression, MAX_SPOTS + 1))
    result = _group(rows[:MAX_SPOTS], _spoken_spot(query), by_count=True)
    result.capped = len(rows) > MAX_SPOTS
    return result


async def chapters(query: Query) -> SpotHits:
    expression = query.full_expression()
    if not expression:
        return SpotHits()
    rows = await db.fetch_all(f"{_CHAPTER_SQL} ORDER BY bm25(chapters_fts) LIMIT ?", (expression, MAX_SPOTS))
    return _group(rows, _chapter_spot)


async def of_video(video_id: str, query: Query) -> VideoSpots:
    """Alle Fundstellen eines Videos für die Vorschau: Titel, Kapitel,
    Gesagtes und ein Ausschnitt der Beschreibung."""
    from app.services.text_resolver import get_description
    expression = query.full_expression()
    spots: list[Spot] = []
    if expression:
        chapter_rows = await db.fetch_all(
            f"{_CHAPTER_SQL} AND c.video_id = ? ORDER BY c.start_time LIMIT ?", (expression, video_id, PREVIEW_SPOTS))
        spoken_rows = await db.fetch_all(
            f"{_SPOKEN_SQL} AND c.video_id = ? ORDER BY c.start LIMIT ?", (expression, video_id, PREVIEW_SPOTS))
        spots = [*map(_chapter_spot, chapter_rows), *map(_spoken_spot(query), spoken_rows)]
        spots.sort(key=lambda spot: spot.start)
    title = await db.fetch_val("SELECT title FROM videos WHERE id = ?", (video_id,)) or ""
    description: Optional[str] = await get_description(video_id) or None
    if description and first_hit(description, query.terms) is not None:
        description = excerpt(description, query.terms, 320)
    elif description:
        description = excerpt(description, [], 320)
    return VideoSpots(video_id=video_id, title_hit=first_hit(title, query.terms) is not None,
                      description=description, spots=spots)
