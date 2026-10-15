"""
TubeVault - Modelle zur Sprache (Katalog, Zähler, Setzen von Hand)
"""
from typing import Optional

from pydantic import BaseModel, Field


class LanguageInfo(BaseModel):
    code: str
    name: str                          # deutscher Name, z.B. "Englisch"
    flag: Optional[str] = None         # Flaggen-Zeichen, None = keine passende Flagge


class LanguageSourceInfo(BaseModel):
    key: str                           # hand | quelle | untertitel | text | kanal
    label: str                         # so heißt die Herkunft in der Oberfläche
    rank: int                          # höher gewinnt


class LanguageCatalog(BaseModel):
    """Alles, was die Oberfläche zum Anzeigen einer Sprachangabe braucht."""
    languages: list[LanguageInfo]
    sources: list[LanguageSourceInfo]
    unknown: LanguageInfo              # Filterwert "ohne Sprache"
    mixed: LanguageInfo                # Kanal mit mehreren Sprachen


class LanguageCount(BaseModel):
    """Zähler je Sprache für einen Filter (code "und" = ohne Sprache)."""
    code: str
    count: int


class LanguageBatchRequest(BaseModel):
    video_ids: list[str] = Field(min_length=1, max_length=500)
    language: Optional[str] = None     # None = wieder automatisch bestimmen


class LanguageBatchResult(BaseModel):
    updated: int
    language: Optional[str] = None
