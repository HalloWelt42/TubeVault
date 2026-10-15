"""
Sinngemäß verwandt: was die Bedeutungssuche (semantic_index, semantic_items)
findet, ohne dass die Wörter vorkommen. Steht getrennt von den Worttreffern,
damit lose Verwandtes nie vor passenden Titeln landet. Ohne KI-Dienst oder mit
Genauigkeit "aus" bleibt der Bereich leer.
"""
from pydantic import BaseModel

from app.services import semantic_index, semantic_items, transcripts
from app.services.search.models import Spot
from app.services.search.query import Query
from app.services.search.spots import EXCERPT_CHARS
from app.services.search.text import excerpt

# So viele verwandte Kanäle, Playlists und Feed-Einträge kommen dazu
CHANNELS, PLAYLISTS, FEED, LYRICS = 6, 6, 12, 30


class MeaningHits(BaseModel):
    available: bool = False
    videos: list[str] = []                 # beste zuerst
    spots: dict[str, Spot] = {}            # passende Stelle im Gesagten je Video
    channels: list[str] = []
    playlists: list[int] = []
    feed: list[str] = []                   # Video-Kennungen noch nicht geladener Feed-Einträge


async def find(query: Query, precision: str | None) -> MeaningHits:
    if query.empty:
        return MeaningHits()
    level = await semantic_index.precision(precision)
    if not level or not await semantic_index.config() or not await semantic_index.available():
        return MeaningHits()               # aus oder Dienst nicht erreichbar
    text = " ".join(term.text() for term in query.terms)
    scores = dict(await semantic_index.search(text, level) or [])   # None: noch keine Videovektoren
    for video_id, score in await semantic_items.search(text, "lyrics", level, LYRICS):
        scores[video_id] = max(score, scores.get(video_id, score))
    passages = await semantic_index.search_passages(text, level) or []
    by_chunk = await transcripts.passages_by_id([chunk_id for chunk_id, _ in passages])
    spots: dict[str, Spot] = {}
    for chunk_id, score in passages:
        passage = by_chunk.get(chunk_id)
        if not passage or passage.video_id in spots:
            continue
        spots[passage.video_id] = Spot(kind="gesagt", start=passage.start, origin=passage.kind,
                                       text=excerpt(passage.text, [], EXCERPT_CHARS))
        scores[passage.video_id] = max(score, scores.get(passage.video_id, score))
    return MeaningHits(
        available=True,
        videos=sorted(scores, key=lambda video_id: -scores[video_id]),
        spots=spots,
        channels=[ref for ref, _ in await semantic_items.search(text, "channel", level, CHANNELS)],
        playlists=[int(ref) for ref, _ in await semantic_items.search(text, "playlist", level, PLAYLISTS)],
        feed=[ref for ref, _ in await semantic_items.search(text, "feed", level, FEED)],
    )
