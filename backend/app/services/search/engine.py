"""
Die Suche über alle Bereiche: Übersicht ("Alles", Aufklappliste) mit den
besten Treffern und der Zahl je Bereich, ein Bereich seitenweise, die
Fundstellen eines Videos für die Vorschau.

Jeder Bereich zählt nach denselben Filtern; die Sprachzähler gelten vor dem
Sprachfilter (sonst ließe sich eine Sprache nicht mehr dazuwählen).
"""
import json
from collections import Counter
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import language, video_classifier
from app.services.search import catalog, feed, meaning, spots, videos, vocabulary
from app.services.search.filters import SearchFilters
from app.services.search.models import (ChannelHit, FeedHit, Found, Overview, PlaylistHit, Section, SectionPage,
                                        Suggestion, TermInfo, VideoSpots)
from app.services.search.query import Query, parse

# Bereiche, die nur Worttreffer enthalten (für "Meintest du")
_WORD_SECTIONS = ("videos", "gesagt", "kapitel", "musik")


class _Run(BaseModel):
    """Was eine Suche einmal berechnet und mehrere Bereiche teilen."""
    query: Query
    filters: SearchFilters
    shorts_excluded: bool
    words: Optional[videos.WordHits] = None
    spoken: Optional[spots.SpotHits] = None
    chapters: Optional[spots.SpotHits] = None


async def _run(text: str, filters: SearchFilters) -> _Run:
    query = parse(text)
    return _Run(query=query, filters=filters.effective(query),
                shorts_excluded=await video_classifier.shorts_excluded())


async def _words(run: _Run) -> videos.WordHits:
    if run.words is None:
        run.words = await videos.word_hits(run.query)
    return run.words


async def _spoken(run: _Run) -> spots.SpotHits:
    if run.spoken is None:
        run.spoken = await spots.spoken(run.query)
    return run.spoken


async def _chapters(run: _Run) -> spots.SpotHits:
    if run.chapters is None:
        run.chapters = await spots.chapters(run.query)
    return run.chapters


async def _filtered(run: _Run, ids: list[str]) -> videos.Filtered:
    return await videos.apply_filters(ids, run.filters, shorts_excluded=run.shorts_excluded,
                                      keep_order=run.filters.order == "passend")


def _page(ids: list, page: int, per_page: int) -> list:
    start = (page - 1) * per_page
    return ids[start:start + per_page]


async def _videos_page(run: _Run, page: int, per_page: int) -> tuple[SectionPage, videos.Filtered]:
    words, spoken = await _words(run), await _spoken(run)
    filtered = await _filtered(run, words.order)
    found = {video_id: [*places, *([Found(where="gesagt", count=spoken.counts[video_id])]
                                    if video_id in spoken.counts else [])]
             for video_id, places in words.found.items()}
    items = await videos.hits(_page(filtered.ids, page, per_page), found)
    return SectionPage(section="videos", total=len(filtered.ids), items=items, page=page, per_page=per_page), filtered


async def _spots_page(run: _Run, section: Section, hits: spots.SpotHits, page: int, per_page: int) -> SectionPage:
    filtered = await _filtered(run, hits.order)
    items = await videos.hits(_page(filtered.ids, page, per_page))
    where = "gesagt" if section == "gesagt" else "kapitel"
    for item in items:
        item.spots = hits.spots.get(item.id, [])
        item.spot_count = hits.counts.get(item.id, 0)
        item.found = [Found(where=where, count=item.spot_count)]
    return SectionPage(section=section, total=len(filtered.ids), more=hits.capped, items=items,
                       page=page, per_page=per_page)


async def _channel_counts(video_ids: list[str]) -> dict[str, int]:
    if not video_ids:
        return {}
    rows = await db.fetch_all(
        "SELECT v.channel_id, COUNT(*) FROM json_each(?) j CROSS JOIN videos v ON v.id = j.value GROUP BY v.channel_id",
        (json.dumps(video_ids),))
    return {row[0]: row[1] for row in rows if row[0]}


def _paged(section: Section, items: list, page: int, per_page: int) -> SectionPage:
    return SectionPage(section=section, total=len(items), items=_page(items, page, per_page), page=page, per_page=per_page)


async def _meaning_page(run: _Run, found: meaning.MeaningHits, page: int, per_page: int) -> SectionPage:
    taken = set((await _words(run)).order) | set((await _spoken(run)).order) | set((await _chapters(run)).order)
    filtered = await _filtered(run, [video_id for video_id in found.videos if video_id not in taken])
    items = await videos.hits(_page(filtered.ids, page, per_page))
    for item in items:
        item.meaning = True
        if item.id in found.spots:
            item.spots = [found.spots[item.id]]
            item.spot_count = 1
    return SectionPage(section="sinngemaess", total=len(filtered.ids), items=items, page=page, per_page=per_page)


async def _with_meaning_channels(items: list[ChannelHit], ids: list[str]) -> list[ChannelHit]:
    known = {hit.channel_id for hit in items}
    extra = [channel_id for channel_id in ids if channel_id not in known]
    if not extra:
        return items
    rows = await db.fetch_all(
        "SELECT channel_id, channel_name, language FROM subscriptions WHERE channel_id IN (SELECT value FROM json_each(?))",
        (json.dumps(extra),))
    by_id = {row["channel_id"]: row for row in rows}
    return [*items, *(ChannelHit(channel_id=i, channel_name=by_id[i]["channel_name"] or i, subscribed=True,
                                 language=by_id[i]["language"], meaning=True) for i in extra if i in by_id)]


async def _with_meaning_playlists(items: list[PlaylistHit], ids: list[int]) -> list[PlaylistHit]:
    known = {hit.id for hit in items}
    extra = [playlist_id for playlist_id in ids if playlist_id not in known]
    if not extra:
        return items
    rows = await db.fetch_all(
        "SELECT id, name, description, video_count FROM playlists WHERE id IN (SELECT value FROM json_each(?))",
        (json.dumps(extra),))
    by_id = {row["id"]: row for row in rows}
    return [*items, *(PlaylistHit(id=i, name=by_id[i]["name"] or "", description=by_id[i]["description"],
                                  video_count=by_id[i]["video_count"] or 0, meaning=True) for i in extra if i in by_id)]


async def _feed_page(run: _Run, found: Optional[meaning.MeaningHits], page: int,
                     per_page: int) -> tuple[SectionPage, feed.FeedResult]:
    result = await feed.search(run.query, run.filters, shorts_excluded=run.shorts_excluded)
    items: list[FeedHit] = await feed.hits(_page(result.ids, page, per_page))
    total = result.total
    if found and found.feed and run.filters.feed_applies and page * per_page >= total:
        # Sinngemäß Verwandtes hinter den Worttreffern, nur ungeladene und nicht schon gezeigte
        have = result.video_ids
        rows = await db.fetch_all(
            """SELECT MIN(r.id) AS id FROM rss_entries r WHERE r.video_id IN (SELECT value FROM json_each(?))
               AND NOT EXISTS (SELECT 1 FROM videos v WHERE v.id = r.video_id AND v.status = 'ready')
               AND COALESCE(r.dismissed, 0) = 0 GROUP BY r.video_id""",
            (json.dumps([video_id for video_id in found.feed if video_id not in have]),))
        extra = await feed.hits([row["id"] for row in rows])
        for hit in extra:
            hit.meaning = True
        total += len(extra)
        items = [*items, *extra][:per_page]
    return SectionPage(section="abos", total=total, items=items, page=page, per_page=per_page), result


async def overview(text: str, filters: SearchFilters, *, limit: int = 5, with_meaning: bool = True) -> Overview:
    """Alle Bereiche auf einmal: je Bereich die besten limit Treffer und die Zahl."""
    run = await _run(text, filters)
    query = run.query
    terms = [TermInfo(words=term.words, prefix=term.prefix) for term in query.terms]
    if query.empty:
        return Overview(query=query.text, terms=terms, filters=run.filters, sections={})

    found = await meaning.find(query, run.filters.precision) if with_meaning else meaning.MeaningHits()
    video_page, filtered = await _videos_page(run, 1, limit)
    sections: dict[str, SectionPage] = {"videos": video_page}
    sections["gesagt"] = await _spots_page(run, "gesagt", await _spoken(run), 1, limit)
    sections["kapitel"] = await _spots_page(run, "kapitel", await _chapters(run), 1, limit)
    sections["abos"], feed_words = await _feed_page(run, found, 1, limit)
    channels = await catalog.channels(query, await _channel_counts(filtered.ids), run.words.channels)
    sections["kanaele"] = _paged("kanaele", await _with_meaning_channels(channels, found.channels), 1, limit)
    playlists = await catalog.playlists(query)
    sections["playlists"] = _paged("playlists", await _with_meaning_playlists(playlists, found.playlists), 1, limit)
    sections["musik"] = _paged("musik", await catalog.music(query), 1, limit)
    sections["sinngemaess"] = await _meaning_page(run, found, 1, limit)

    # Sprachen über alle gefundenen Videos und Feed-Einträge, vor dem Sprachfilter
    all_ids = list(dict.fromkeys([*run.words.order, *run.spoken.order, *run.chapters.order]))
    unfiltered = run.filters.model_copy(update={"languages": []})
    counted = await videos.apply_filters(all_ids, unfiltered, shorts_excluded=run.shorts_excluded)
    counts = Counter(counted.language_counts) + Counter(feed_words.language_counts)
    language_counts = language.counts_from_rows(counts.items())

    # Meintest du: nur wenn kein Wort getroffen hat (Sinngemäßes allein zählt nicht)
    word_hits = (sum(sections[name].total for name in _WORD_SECTIONS) + feed_words.total
                 + sum(not hit.meaning for hit in sections["kanaele"].items)
                 + sum(not hit.meaning for hit in sections["playlists"].items))
    suggestion = await _suggestion(query, run.filters) if not word_hits else None
    return Overview(query=query.text, terms=terms, filters=run.filters, sections=sections,
                    language_counts=language_counts, semantic=found.available, suggestion=suggestion)


async def _suggestion(query: Query, filters: SearchFilters) -> Optional[Suggestion]:
    better = await vocabulary.did_you_mean(query)
    if not better:
        return None
    run = await _run(better, filters)
    filtered = await _filtered(run, (await _words(run)).order)
    return Suggestion(text=better, total=len(filtered.ids)) if filtered.ids else None


async def section(name: Section, text: str, filters: SearchFilters, *, page: int = 1, per_page: int = 24) -> SectionPage:
    """Ein Bereich seitenweise."""
    run = await _run(text, filters)
    if run.query.empty:
        return SectionPage(section=name, total=0, items=[], page=page, per_page=per_page)
    if name == "videos":
        return (await _videos_page(run, page, per_page))[0]
    if name == "gesagt":
        return await _spots_page(run, "gesagt", await _spoken(run), page, per_page)
    if name == "kapitel":
        return await _spots_page(run, "kapitel", await _chapters(run), page, per_page)
    if name == "abos":
        found = await meaning.find(run.query, run.filters.precision)
        return (await _feed_page(run, found, page, per_page))[0]
    if name == "kanaele":
        filtered = await _filtered(run, (await _words(run)).order)
        found = await meaning.find(run.query, run.filters.precision)
        channels = await catalog.channels(run.query, await _channel_counts(filtered.ids), run.words.channels)
        return _paged("kanaele", await _with_meaning_channels(channels, found.channels), page, per_page)
    if name == "playlists":
        found = await meaning.find(run.query, run.filters.precision)
        return _paged("playlists", await _with_meaning_playlists(await catalog.playlists(run.query), found.playlists),
                      page, per_page)
    if name == "musik":
        return _paged("musik", await catalog.music(run.query), page, per_page)
    return await _meaning_page(run, await meaning.find(run.query, run.filters.precision), page, per_page)


async def video_ids(text: str, filters: SearchFilters, *, limit: int) -> list[str]:
    """Kennungen der Worttreffer (Bereich Videos), etwa für "Treffer als Playlist"."""
    run = await _run(text, filters)
    if run.query.empty:
        return []
    return (await _filtered(run, (await _words(run)).order)).ids[:limit]


async def spots_of(video_id: str, text: str) -> VideoSpots:
    return await spots.of_video(video_id, parse(text))


async def new_counts(text: str, filters: SearchFilters, *, since: str) -> tuple[int, int]:
    """Neue Treffer seit since: (geladene Videos, Feed-Einträge) - für gemerkte Suchen."""
    run = await _run(text, filters.model_copy(update={"since": since}))
    if run.query.empty:
        return 0, 0
    videos_new = len((await _filtered(run, (await _words(run)).order)).ids)
    feed_new = (await feed.search(run.query, run.filters, shorts_excluded=run.shorts_excluded)).total
    return videos_new, feed_new
