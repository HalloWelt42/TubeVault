"""
Videos nach Wörtern in Titel, Kanal, Kapiteln, Schlagwörtern, Notizen,
Liedtext und Beschreibung (Index: search_index.videos_fts, Kapitel:
chapters_fts) sowie Teilwörtern in Titel und Kanal.

Ordnung "passend": wo das Wort steht, entscheidet zuerst (Titel vor Kanal vor
Kapitel vor Schlagwort, Notiz, Liedtext, Beschreibung, dann Wörter auf
mehrere Felder verteilt, zuletzt Teilwörter); danach ganze Wörter vor
Wortanfängen, dann wer an mehr Stellen trifft, dann die Relevanz des Index. Eine eingetippte Video-Kennung
steht immer vorn.
"""
import json
from collections import Counter
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import language, search_index
from app.services.search import query as query_module
from app.services.search.filters import VIDEO_ORDER, SearchFilters, video_sql
from app.services.search.models import Found, VideoHit
from app.services.search.query import Query

# Felder des Index in der Reihenfolge ihres Gewichts; "kapitel" steht dazwischen
_FIELDS = [("titel", "title"), ("kanal", "channel_name"), ("kapitel", None), ("schlagwort", "tags"),
           ("notiz", "notes"), ("liedtext", "lyrics"), ("beschreibung", "description")]
_SPREAD, _INFIX = len(_FIELDS), len(_FIELDS) + 1


class WordHits(BaseModel):
    """Alle Videos mit Worttreffern, noch ungefiltert."""
    order: list[str] = []                          # passend geordnet
    found: dict[str, list[Found]] = {}
    chapters: dict[str, int] = {}                  # Kapiteltreffer je Video
    channels: dict[str, str] = {}                  # Kanäle, deren Name trifft: Kennung -> Name


async def _ids(sql: str, params: tuple) -> dict[str, float]:
    return {row[0]: row[1] for row in await db.fetch_all(sql, params)}


async def _fts(expression: Optional[str]) -> dict[str, float]:
    """Videos, deren Indexeintrag passt, mit Relevanz (kleiner = besser)."""
    if not expression:
        return {}
    return await _ids(
        f"""SELECT d.video_id, bm25(videos_fts, {search_index.BM25_WEIGHTS})
            FROM videos_fts JOIN search_docs d ON d.doc_id = videos_fts.rowid
            WHERE videos_fts MATCH ?""", (expression,))


async def _fts_ids(expression: Optional[str]) -> set[str]:
    """Nur welche Videos passen (ohne Relevanz, deutlich schneller)."""
    if not expression:
        return set()
    rows = await db.fetch_all(
        """SELECT d.video_id FROM videos_fts JOIN search_docs d ON d.doc_id = videos_fts.rowid
           WHERE videos_fts MATCH ?""", (expression,))
    return {row[0] for row in rows}


async def _chapter_counts(query: Query) -> dict[str, int]:
    expression = query.full_expression()
    if not expression:
        return {}
    rows = await db.fetch_all(
        """SELECT c.video_id, COUNT(*) FROM chapters_fts JOIN chapters c ON c.id = chapters_fts.rowid
           WHERE chapters_fts MATCH ? GROUP BY c.video_id""", (expression,))
    return {row[0]: row[1] for row in rows}


async def word_hits(query: Query) -> WordHits:
    """Worttreffer über alle Felder, passend geordnet, mit den Fundorten."""
    await search_index.refresh_before_query()
    if query.empty:
        return WordHits()
    scores = await _fts(query.expression())
    exact = await _fts_ids(query.expression(prefix=False))
    chapters = await _chapter_counts(query)
    in_field: dict[str, set[str]] = {}
    for name, column in _FIELDS:
        in_field[name] = set(chapters) if column is None else await _fts_ids(query.in_columns(column))
    infix_sql, infix_params = query_module.like_clause(query, ["title", "channel_name"])
    infix = {row[0] for row in await db.fetch_all(
        f"SELECT id FROM videos WHERE status = 'ready' AND {infix_sql}", infix_params)} if infix_sql != "0" else set()
    excluded = await _fts_ids(query.exclusion()) if query.excluded else set()
    # Eine eingetippte Kennung (ein Wort ohne Leerzeichen) darf das Video direkt finden
    typed_id = query.text.strip() if 6 <= len(query.text.strip()) <= 40 and " " not in query.text.strip() else None

    candidates = (set(scores) | set(chapters) | infix | ({typed_id} if typed_id else set())) - excluded
    found: dict[str, list[Found]] = {}
    tiers: dict[str, int] = {}
    for video_id in candidates:
        places = [Found(where=name, count=chapters.get(video_id) if name == "kapitel" else None)
                  for name, _ in _FIELDS if video_id in in_field[name]]
        if video_id in infix and not places:
            places.append(Found(where="teilwort"))
        found[video_id] = places
        tier = next((i for i, (name, _) in enumerate(_FIELDS) if video_id in in_field[name]), None)
        tiers[video_id] = tier if tier is not None else (_SPREAD if video_id in scores else _INFIX)

    def rank(video_id: str):
        if video_id == typed_id:
            return (-1, 0, 0, 0.0)
        # Gleiches Feld: ganze Wörter vor Wortanfängen, dann wer das Wort an mehr Stellen trägt
        # (Titel, Kapitel und Beschreibung: das Thema des Videos), dann die Relevanz des Index
        return (tiers[video_id], 0 if video_id in exact else 1, -len(found[video_id]), scores.get(video_id, 0.0))

    order = sorted(candidates, key=lambda video_id: (rank(video_id), video_id))
    named = in_field["kanal"] - excluded
    channels = {row[0]: row[1] for row in await db.fetch_all(
        """SELECT DISTINCT v.channel_id, v.channel_name FROM json_each(?) j CROSS JOIN videos v ON v.id = j.value
           WHERE v.channel_id IS NOT NULL""", (json.dumps(sorted(named)),))} if named else {}
    return WordHits(order=order, found=found, chapters=chapters, channels=channels)


class Filtered(BaseModel):
    ids: list[str]                                 # nach Filtern und Ordnung
    language_counts: dict[str, int] = {}           # vor dem Sprachfilter


async def apply_filters(ids: list[str], filters: SearchFilters, *, shorts_excluded: bool,
                        keep_order: bool = True) -> Filtered:
    """Video-Kennungen filtern; keep_order=False ordnet nach filters.order
    (neu, alt, lang ...), sonst bleibt die übergebene (passende) Reihenfolge."""
    if not ids:
        return Filtered(ids=[])
    where, params = video_sql(filters, "v", shorts_excluded=shorts_excluded, with_language=False)
    order = "" if keep_order or filters.order not in VIDEO_ORDER else f" ORDER BY {VIDEO_ORDER[filters.order]}"
    # CROSS JOIN legt die Reihenfolge fest: erst die Kennungen, dann je eine Zeile nachschlagen
    rows = await db.fetch_all(
        f"""SELECT v.id, {language.code_sql('v.language')} AS code FROM json_each(?) j CROSS JOIN videos v
            ON v.id = j.value WHERE {where}{order}""",
        (json.dumps(ids), *params))
    counts = Counter(row["code"] for row in rows)
    wanted = set(filters.languages)
    kept = [row["id"] for row in rows if not wanted or row["code"] in wanted]
    if keep_order:
        position = {video_id: index for index, video_id in enumerate(ids)}
        kept.sort(key=lambda video_id: position[video_id])
    return Filtered(ids=kept, language_counts=dict(counts))


_HIT_COLUMNS = ("id, title, channel_id, channel_name, duration, upload_date, view_count, language, "
                "language_source, is_archived, source, video_type, last_position")


async def hits(video_ids: list[str], found: Optional[dict[str, list[Found]]] = None) -> list[VideoHit]:
    """Treffer zum Anzeigen, in der übergebenen Reihenfolge."""
    if not video_ids:
        return []
    rows = await db.fetch_all(
        f"SELECT {', '.join('v.' + c.strip() for c in _HIT_COLUMNS.split(','))} "
        f"FROM json_each(?) j CROSS JOIN videos v ON v.id = j.value", (json.dumps(video_ids),))
    by_id = {row["id"]: row for row in rows}
    result = []
    for video_id in video_ids:
        row = by_id.get(video_id)
        if not row:
            continue
        data = dict(row)
        data["title"] = data["title"] or video_id
        data["is_archived"] = bool(data["is_archived"])
        result.append(VideoHit(**data, found=(found or {}).get(video_id, [])))
    return result
