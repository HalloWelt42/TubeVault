"""
Suchtext verstehen.

Suchsprache (steht so auch auf der Suche-Seite):
  Wort             Wortanfang ab PREFIX_MIN Zeichen ("Kernfu" findet "Kernfusion"),
                   kürzere Wörter nur ganz ("Lem" findet nicht "Lemma")
  "Wortfolge"      genau diese Wörter hintereinander
  -Wort            Treffer mit diesem Wort weglassen (auch -"Wortfolge")
  A oder B         eins von beiden reicht (auch ODER, OR, |)
  kanal:Name       nur Kanäle, deren Name das enthält (kanal:"media.ccc.de")
  sprache:en       nur diese Sprache (Kürzel oder Name: sprache:englisch)
  länge:>20        Minuten: >20, <10, 10-30; länge:20 heißt mindestens 20
  jahr:2024        hochgeladen in dem Jahr; jahr:2020-2024, jahr:>2020
  in:archiv        nur Archiv; in:bibliothek, in:eigene

Alle Wörter und Gruppen sind UND-verknüpft. Eine Angabe, die sich nicht
lesen lässt (länge:viel), zählt als gewöhnliche Wörter.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel

from app.services import language
from app.services.search.text import PREFIX_MIN, WORD, fold

Location = Literal["bibliothek", "archiv", "eigene"]

_OR_WORDS = {"oder", "or", "|"}
_OPERATORS = {"kanal": "channel", "sprache": "language", "länge": "length", "laenge": "length",
              "dauer": "length", "jahr": "year", "in": "location"}
_LOCATIONS = {"archiv": "archiv", "bibliothek": "bibliothek", "eigene": "eigene", "eigen": "eigene"}
_KEY = re.compile(r"([^\W\d_]+):(?=\S)", re.UNICODE)
_MINUTES = re.compile(r"^(>=|<=|>|<)?(\d{1,4})(?:-(\d{1,4}))?$")
_YEARS = re.compile(r"^(>=|<=|>|<)?(\d{4})(?:-(\d{4}))?$")


class Term(BaseModel):
    """Ein Suchbegriff: ein Wort oder mehrere Wörter hintereinander."""
    words: list[str]
    phrase: bool = False          # in Anführungszeichen: genau so, kein Wortanfang

    @property
    def prefix(self) -> bool:
        """Darf das letzte Wort als Wortanfang treffen?"""
        return not self.phrase and len(fold(self.words[-1])) >= PREFIX_MIN

    def fts(self, prefix: bool = True) -> str:
        star = "*" if prefix and self.prefix else ""
        return f'"{" ".join(self.words)}"{star}'

    def text(self) -> str:
        joined = " ".join(self.words)
        return f'"{joined}"' if self.phrase else joined


class Operators(BaseModel):
    """Angaben aus dem Suchtext, die wie Filter wirken."""
    channel: Optional[str] = None
    languages: list[str] = []
    min_seconds: Optional[int] = None
    max_seconds: Optional[int] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    location: Optional[Location] = None


class Query(BaseModel):
    text: str
    groups: list[list[Term]] = []     # UND über die Gruppen, ODER innerhalb
    excluded: list[Term] = []
    operators: Operators = Operators()

    @property
    def empty(self) -> bool:
        return not self.groups

    @property
    def terms(self) -> list[Term]:
        """Alle gesuchten Begriffe (zum Hervorheben und für Ausschnitte)."""
        return [term for group in self.groups for term in group]

    def expression(self, prefix: bool = True) -> Optional[str]:
        """Volltext-Ausdruck der gesuchten Begriffe (ohne Ausschlüsse)."""
        if not self.groups:
            return None
        parts = []
        for group in self.groups:
            alternatives = [term.fts(prefix) for term in group]
            parts.append(alternatives[0] if len(alternatives) == 1 else f"({' OR '.join(alternatives)})")
        return " AND ".join(parts)

    def exclusion(self) -> Optional[str]:
        """Volltext-Ausdruck der Ausschlüsse (irgendeiner genügt zum Weglassen)."""
        if not self.excluded:
            return None
        return " OR ".join(term.fts(prefix=False) for term in self.excluded)

    def full_expression(self, prefix: bool = True) -> Optional[str]:
        """Gesuchtes ohne Ausgeschlossenes - für Indexe, deren Einträge für sich
        stehen (Abschnitte des Gesagten, Kapitel, Feed)."""
        positive = self.expression(prefix)
        if not positive or not self.excluded:
            return positive
        return f"({positive}) NOT ({self.exclusion()})"

    def in_columns(self, columns: str, prefix: bool = True) -> Optional[str]:
        """Ausdruck nur in bestimmten Spalten ("title" oder "tags notes")."""
        positive = self.expression(prefix)
        return f"{{{columns}}} : ({positive})" if positive else None


class _Raw(BaseModel):
    negative: bool
    key: Optional[str]                # erkannte Angabe (channel, language, ...)
    typed: Optional[str] = None       # so getippt ("länge")
    value: str
    quoted: bool


def _scan(text: str) -> list[_Raw]:
    """Suchtext in Stücke zerlegen: -, schluessel:, "Wortfolge" oder Wort."""
    raws, i, n = [], 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        negative = text[i] == "-" and i + 1 < n and not text[i + 1].isspace()
        if negative:
            i += 1
        key = typed = None
        found = _KEY.match(text, i)
        if found and found.group(1).lower() in _OPERATORS:
            typed = found.group(1)
            key = _OPERATORS[typed.lower()]
            i = found.end()
        if i < n and text[i] == '"':
            end = text.find('"', i + 1)
            end = n if end < 0 else end
            raws.append(_Raw(negative=negative, key=key, typed=typed, value=text[i + 1:end], quoted=True))
            i = end + 1
        else:
            end = i
            while end < n and not text[end].isspace():
                end += 1
            raws.append(_Raw(negative=negative, key=key, typed=typed, value=text[i:end], quoted=False))
            i = end
    return raws


def _minutes(value: str) -> Optional[tuple[Optional[int], Optional[int]]]:
    found = _MINUTES.match(value.replace(" ", ""))
    if not found:
        return None
    sign, first, second = found.groups()
    low, high = int(first) * 60, int(second) * 60 if second else None
    if second:
        return (min(low, high), max(low, high))
    return {"<": (None, low), "<=": (None, low)}.get(sign, (low, None))


def _years(value: str) -> Optional[tuple[Optional[int], Optional[int]]]:
    found = _YEARS.match(value.replace(" ", ""))
    if not found:
        return None
    sign, first, second = found.groups()
    low = int(first)
    if second:
        return (min(low, int(second)), max(low, int(second)))
    return {">": (low + 1, None), ">=": (low, None), "<": (None, low - 1), "<=": (None, low)}.get(sign, (low, low))


def _apply_operator(operators: Operators, key: str, value: str) -> bool:
    """Angabe übernehmen; False, wenn sie sich nicht lesen lässt."""
    value = value.strip()
    if not value:
        return False
    if key == "channel":
        operators.channel = value
    elif key == "language":
        codes = [language.from_user(part) for part in value.split(",")]
        if not all(codes):
            return False
        operators.languages = list(dict.fromkeys([*operators.languages, *codes]))
    elif key == "length":
        span = _minutes(value)
        if not span:
            return False
        operators.min_seconds, operators.max_seconds = span
    elif key == "year":
        span = _years(value)
        if not span:
            return False
        operators.year_from, operators.year_to = span
    elif key == "location":
        location = _LOCATIONS.get(value.lower())
        if not location:
            return False
        operators.location = location
    return True


def _term(value: str, quoted: bool) -> Optional[Term]:
    words = [word.lower() for word in WORD.findall(value)]
    return Term(words=words, phrase=quoted and len(words) > 0) if words else None


def parse(text: str) -> Query:
    """Suchtext in Begriffe, Ausschlüsse und Angaben zerlegen."""
    query = Query(text=(text or "").strip())
    operators = Operators()
    join_next = False
    for raw in _scan(query.text):
        if raw.key and not raw.negative and _apply_operator(operators, raw.key, raw.value):
            continue
        if not raw.key and not raw.quoted and not raw.negative and raw.value.lower() in _OR_WORDS and query.groups:
            join_next = True
            continue
        # Eine unlesbare Angabe ("länge:viel") zählt als zwei gewöhnliche Wörter
        pieces = [(raw.typed, False), (raw.value, raw.quoted)] if raw.key else [(raw.value, raw.quoted)]
        for value, quoted in pieces:
            term = _term(value, quoted)
            if not term:
                continue
            if raw.negative:
                query.excluded.append(term)
            elif join_next:
                query.groups[-1].append(term)
            else:
                query.groups.append([term])
            join_next = False
    query.operators = operators
    return query


def like_clause(query: Query, columns: list[str]) -> tuple[str, list]:
    """Teilwort-Suche ("teig" findet "Sauerteig") über einfache Textspalten:
    jede Gruppe muss in einer der Spalten vorkommen. Kurze Wörter zählen hier
    nicht (sonst fände "lem" jedes "Problem"); None-Ergebnis als "0"."""
    clauses, params = [], []
    for group in query.groups:
        alternatives = []
        for term in group:
            needle = " ".join(term.words)
            if len(fold(needle)) < PREFIX_MIN:
                continue
            pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            alternatives.append("(" + " OR ".join(f"{column} LIKE ? ESCAPE '\\'" for column in columns) + ")")
            params.extend([pattern] * len(columns))
        if not alternatives:
            return "0", []
        clauses.append("(" + " OR ".join(alternatives) + ")")
    return (" AND ".join(clauses) if clauses else "0"), params
