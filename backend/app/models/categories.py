"""
TubeVault - Kategorien: Datenmodelle

Eine Kategorie sammelt Videos auf zwei Wegen:
  von Hand    ein Video wird hineingelegt oder herausgenommen; das bleibt so
  per Regel   "Kanal ist", "Schlagwort enthält", "Inhaltlich wie" - passende
              Videos kommen hinein, neue auch
Was von Hand herausgenommen wurde, bringt keine Regel zurück.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

RuleKind = Literal["channel", "tag", "semantic"]
Origin = Literal["hand", "rule"]
# Warum ein Video in der Kategorie ist: von Hand oder die Art der Regel
Reason = Literal["hand", "channel", "tag", "semantic"]

# Feste Farbfelder (kein freier Farbwähler); neue Kategorien bekommen die
# nächste noch freie Farbe
CATEGORY_COLORS = [
    "#F44336", "#E91E63", "#9C27B0", "#673AB7", "#3F51B5", "#2196F3",
    "#03A9F4", "#00BCD4", "#009688", "#4CAF50", "#8BC34A", "#CDDC39",
    "#FFEB3B", "#FFC107", "#FF9800", "#FF5722", "#795548", "#607D8B",
]

NAME_MAX = 80
DESCRIPTION_MAX = 300
RULE_VALUE_MAX = 200


def _clean(text: Optional[str]) -> Optional[str]:
    return " ".join(text.split()) if isinstance(text, str) else text


class RuleIn(BaseModel):
    """Eine Regel, wie die Oberfläche sie schickt.
    channel: value ist die Kanal-Kennung; tag: das Wort; semantic: die
    Beschreibung, precision die Stufe (weit, ausgewogen, genau, sehr_genau)."""
    kind: RuleKind
    value: str = Field(min_length=1, max_length=RULE_VALUE_MAX)
    precision: Optional[str] = None

    @field_validator("value", mode="before")
    @classmethod
    def _strip(cls, value):
        return _clean(value)


class Rule(RuleIn):
    id: int
    label: str                      # Anzeige: Kanalname bzw. der Wert


class _Named(BaseModel):
    @field_validator("name", "description", mode="before", check_fields=False)
    @classmethod
    def _clean_text(cls, value):
        return _clean(value)


class CategoryCreate(_Named):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX)
    color: Optional[str] = None     # aus CATEGORY_COLORS, sonst die nächste freie
    rules: list[RuleIn] = Field(default_factory=list, max_length=20)


class CategoryUpdate(_Named):
    name: Optional[str] = Field(None, min_length=1, max_length=NAME_MAX)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX)
    color: Optional[str] = None


class RulesUpdate(BaseModel):
    rules: list[RuleIn] = Field(default_factory=list, max_length=20)


class CategoryCard(BaseModel):
    """Eine Kategorie in der Übersicht."""
    id: int
    name: str
    description: Optional[str] = None
    color: str
    video_count: int = 0
    duration: int = 0               # Sekunden
    finished_count: int = 0         # davon gesehen
    cover_ids: list[str] = []       # die ersten Videos (Bildcollage)
    rules: list[Rule] = []
    last_filled_at: Optional[str] = None   # zuletzt kam ein Video hinein
    created_at: Optional[str] = None


class CategoryBrief(BaseModel):
    """Kurzform für Auswahllisten (Wiedergabe, Filter)."""
    id: int
    name: str
    description: Optional[str] = None
    color: str
    video_count: int = 0


class ChannelCount(BaseModel):
    channel_id: str
    name: str
    count: int


class PrecisionChoice(BaseModel):
    key: str
    label: str


class AiState(BaseModel):
    semantic: bool                  # "Inhaltlich wie" lässt sich neu anlegen
    topics: bool                    # "Themen erkennen" steht zur Verfügung
    precisions: list[PrecisionChoice]
    default_precision: str


class CategoryOverview(BaseModel):
    categories: list[CategoryCard]
    total: int                      # fertige Videos insgesamt
    assigned: int                   # davon in mindestens einer Kategorie
    unassigned: int
    unsorted_channels: list[ChannelCount]
    colors: list[str]
    ai: AiState


class PreviewRequest(BaseModel):
    category_id: Optional[int] = None   # leer: Entwurf einer neuen Kategorie
    rules: list[RuleIn] = Field(default_factory=list, max_length=20)


class PreviewVideo(BaseModel):
    id: str
    title: str
    channel_name: Optional[str] = None


class RulePreview(BaseModel):
    matching: int                   # so viele Videos passen (ohne von Hand Entfernte)
    new: int                        # davon noch nicht in der Kategorie
    leaving: int                    # bisher per Regel drin, passen nicht mehr
    per_rule: list[int]             # Treffer je Regel, in der Reihenfolge der Regeln
    samples: list[PreviewVideo]     # Beispiele, bevorzugt neue
    semantic_missing: bool = False  # eine "Inhaltlich wie"-Regel ließ sich gerade nicht rechnen


class ApplyResult(BaseModel):
    added: int
    removed: int


class VideoIds(BaseModel):
    video_ids: list[str] = Field(min_length=1, max_length=20000)


class Membership(BaseModel):
    """Ein Video in einer Kategorie (für Rückgängig beim Herausnehmen)."""
    video_id: str
    origin: Origin
    rule_id: Optional[int] = None
    position: int = 0
    added_at: Optional[str] = None


class RestoreRequest(BaseModel):
    entries: list[Membership] = Field(min_length=1, max_length=20000)


class ChannelChoice(BaseModel):
    channel_id: str
    name: str
    count: int


class TopicSuggestion(BaseModel):
    id: int
    name: str
    query: str                      # Text der Regel "Inhaltlich wie"
    precision: str
    match_count: int
    channels: list[str] = []        # die häufigsten Kanäle unter den passenden Videos


class TopicState(BaseModel):
    running: bool = False
    phase: Optional[str] = None
    done: int = 0
    total: int = 0
    error: Optional[str] = None
    finished_at: Optional[str] = None
    suggestions: list[TopicSuggestion] = []


class TopicAccept(_Named):
    """Übernehmen, wahlweise mit Änderungen aus dem Seitenblatt."""
    name: Optional[str] = Field(None, min_length=1, max_length=NAME_MAX)
    color: Optional[str] = None
    rules: Optional[list[RuleIn]] = Field(None, max_length=20)
