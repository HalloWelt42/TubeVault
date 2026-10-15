"""
Bei Abos, noch nicht geladen: Feed-Einträge nach Wörtern in Titel, Kanal,
Beschreibung und Schlagwörtern (search.index.feed_fts).

Ordnung "passend": Treffer im Titel zuerst, dann die neuesten. Bewusst ohne
Relevanzrechnung und ohne Teilwörter: es sind über hunderttausend Einträge,
und neu vor alt ist im Feed die natürliche Folge.
"""
import json

from pydantic import BaseModel

from app.database import db
from app.services import language
from app.services.search.filters import FEED_ORDER, SearchFilters, feed_sql
from app.services.search.models import FeedHit
from app.services.search.query import Query

# Mehr Einträge braucht keine Seite; die Zahl bleibt trotzdem genau
MAX_IDS = 5000

_FROM = """FROM feed_fts f JOIN rss_entries r ON r.id = f.rowid
           LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           WHERE feed_fts MATCH ?"""


class FeedResult(BaseModel):
    ids: list[int] = []                        # rss_entries.id, geordnet und gefiltert
    video_ids: set[str] = set()                # die Videos dahinter (die gelieferten)
    total: int = 0
    language_counts: dict[str, int] = {}       # vor dem Sprachfilter


async def search(query: Query, filters: SearchFilters, *, shorts_excluded: bool) -> FeedResult:
    if query.empty or not filters.feed_applies:
        return FeedResult()
    expression = query.full_expression()
    where, params = feed_sql(filters, "r", "s", shorts_excluded=shorts_excluded, with_language=False)
    counts = {row[0]: row[1] for row in await db.fetch_all(
        f"""SELECT {language.code_sql('r.language')} AS code, COUNT(DISTINCT r.video_id)
            {_FROM} AND {where} GROUP BY code""", (expression, *params))}
    if not counts:
        return FeedResult()
    language_where, language_params = "", []
    if filters.languages:
        sql, codes = language.filter_sql("r.language", filters.languages)
        language_where, language_params = f" AND {sql}", codes
    order = FEED_ORDER.get(filters.order, "r.published DESC, r.id")
    title_first = "" if filters.order in FEED_ORDER else \
        "r.id NOT IN (SELECT rowid FROM feed_fts WHERE feed_fts MATCH ?), "
    title_params = [query.in_columns("title")] if title_first else []
    rows = await db.fetch_all(
        f"""SELECT r.id, r.video_id {_FROM} AND {where}{language_where}
            ORDER BY {title_first}{order} LIMIT ?""",
        (expression, *params, *language_params, *title_params, MAX_IDS))
    seen: set[str] = set()
    ids = []
    for row in rows:
        if row["video_id"] not in seen:        # dasselbe Video in mehreren Feeds
            seen.add(row["video_id"])
            ids.append(row["id"])
    wanted = set(filters.languages)
    total = sum(n for code, n in counts.items() if not wanted or code in wanted)
    return FeedResult(ids=ids, video_ids=seen, total=total, language_counts=counts)


async def hits(entry_ids: list[int]) -> list[FeedHit]:
    """Einträge zum Anzeigen, in der übergebenen Reihenfolge, mit Stand der Warteschlange."""
    if not entry_ids:
        return []
    rows = await db.fetch_all(
        """SELECT r.id, r.video_id, r.title, r.channel_id, s.channel_name, r.published, r.duration,
                  r.language, r.language_source, r.video_type,
                  EXISTS (SELECT 1 FROM jobs j WHERE j.type = 'download'
                          AND json_extract(j.metadata, '$.video_id') = r.video_id
                          AND j.status IN ('queued', 'active', 'retry_wait')) AS in_queue
           FROM json_each(?) e CROSS JOIN rss_entries r ON r.id = e.value
           LEFT JOIN subscriptions s ON s.channel_id = r.channel_id""", (json.dumps(entry_ids),))
    by_id = {row["id"]: row for row in rows}
    return [FeedHit(**{**dict(by_id[i]), "title": by_id[i]["title"] or by_id[i]["video_id"],
                       "in_queue": bool(by_id[i]["in_queue"])})
            for i in entry_ids if i in by_id]
