"""Antworten der Suche: Treffer je Bereich, Fundstellen, Übersicht."""
from typing import Literal, Optional

from pydantic import BaseModel

from app.services.language import LanguageCount
from app.services.music_library import Track
from app.services.search.filters import SearchFilters

Section = Literal["videos", "gesagt", "kapitel", "abos", "kanaele", "playlists", "musik", "sinngemaess"]
SECTIONS: tuple[Section, ...] = ("videos", "gesagt", "kapitel", "abos", "kanaele", "playlists", "musik", "sinngemaess")

# Wo ein Video getroffen wurde (Kennzeichen am Treffer, Reihenfolge = Gewicht)
FoundIn = Literal["titel", "kanal", "kapitel", "schlagwort", "notiz", "liedtext", "beschreibung", "teilwort", "gesagt"]


class Found(BaseModel):
    where: FoundIn
    count: Optional[int] = None        # bei Kapiteln und Gesagtem: wie viele Stellen


class Spot(BaseModel):
    """Fundstelle mit Zeit im Video (Kapitel oder Gesagtes)."""
    kind: Literal["kapitel", "gesagt"]
    start: float
    text: str
    origin: Optional[str] = None       # Gesagtes: manual | auto | ai (transcripts.KIND_LABELS)


class VideoHit(BaseModel):
    id: str
    title: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    language: Optional[str] = None
    language_source: Optional[str] = None
    is_archived: bool = False
    source: Optional[str] = None
    video_type: Optional[str] = None
    last_position: Optional[int] = None
    found: list[Found] = []
    spots: list[Spot] = []             # Gesagtes, Kapitel, Sinngemäßes: die Stellen dazu
    spot_count: int = 0                # so viele Stellen insgesamt (spots zeigt die besten)
    meaning: bool = False              # nur sinngemäß verwandt


class FeedHit(BaseModel):
    """Feed-Eintrag eines Abos, noch nicht geladen."""
    id: int
    video_id: str
    title: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    published: Optional[str] = None
    duration: Optional[int] = None
    language: Optional[str] = None
    language_source: Optional[str] = None
    video_type: Optional[str] = None
    in_queue: bool = False
    meaning: bool = False


class ChannelHit(BaseModel):
    channel_id: str
    channel_name: str
    subscribed: bool
    videos: int = 0                    # Videos dieses Kanals unter den Treffern
    language: Optional[str] = None
    meaning: bool = False


class PlaylistHit(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    video_count: int = 0
    meaning: bool = False


class MusicHit(BaseModel):
    """Titel der eigenen Musiksammlung, abspielbar wie in der Musik."""
    track: Track
    year: Optional[int] = None
    genre: Optional[str] = None
    found: list[Literal["titel", "kuenstler", "album", "genre", "liedtext"]] = []


class SectionPage(BaseModel):
    section: Section
    total: int
    more: bool = False                 # total ist eine Untergrenze (Bereich gedeckelt, siehe spots)
    items: list[VideoHit | FeedHit | ChannelHit | PlaylistHit | MusicHit]
    page: int = 1
    per_page: int = 0


class TermInfo(BaseModel):
    """Ein gesuchter Begriff zum Hervorheben (Wortanfang oder ganz)."""
    words: list[str]
    prefix: bool


class Suggestion(BaseModel):
    """Meintest du: verbesserter Suchtext und was er findet."""
    text: str
    total: int


class Overview(BaseModel):
    query: str
    terms: list[TermInfo]
    filters: SearchFilters                       # wirksam (samt Angaben im Suchtext)
    sections: dict[str, SectionPage]
    language_counts: list[LanguageCount] = []    # Videos und Feed, ohne Sprachfilter
    semantic: bool = False                       # Bedeutungssuche war dabei
    suggestion: Optional[Suggestion] = None


class VideoSpots(BaseModel):
    """Alle Fundstellen eines Videos (Vorschau rechts)."""
    video_id: str
    title_hit: bool
    description: Optional[str] = None           # Ausschnitt um die Fundstelle
    spots: list[Spot]
