"""
Filter der Suche und ihre SQL-Bausteine.

Die Seite bietet Sprache, Länge, Zeitraum, Ort, Stand und Ordnung an; Angaben
im Suchtext (kanal:, sprache:, länge:, jahr:, in:) wirken genauso und gehen
den Feldern der Seite vor (effective). Für Videos und Feed-Einträge gibt es
je einen Baustein, damit beide nach denselben Regeln gefiltert werden.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app.services import language, watch_state
from app.services.search.query import Location, Query

Length = Literal["kurz", "mittel", "lang", "sehr_lang"]
Period = Literal["woche", "monat", "jahr"]
Order = Literal["passend", "neu", "alt", "lang", "kurz", "aufrufe"]

# Längen in Sekunden (von, bis); bis None = offen
LENGTHS: dict[str, tuple[int, Optional[int]]] = {
    "kurz": (0, 4 * 60), "mittel": (4 * 60, 20 * 60), "lang": (20 * 60, 60 * 60), "sehr_lang": (60 * 60, None)}
PERIOD_DAYS = {"woche": 7, "monat": 31, "jahr": 365}


class SearchFilters(BaseModel):
    languages: list[str] = []
    length: Optional[Length] = None
    period: Optional[Period] = None
    location: Optional[Location] = None
    state: Optional[watch_state.State] = None
    order: Order = "passend"
    precision: Optional[str] = None     # Bedeutungssuche (semantic_index); leer = Einstellung
    # aus dem Suchtext oder intern
    channel: Optional[str] = None
    min_seconds: Optional[int] = None
    max_seconds: Optional[int] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    since: Optional[str] = None         # nur Neues seit (gemerkte Suchen), "YYYY-MM-DD HH:MM:SS"

    def effective(self, query: Query) -> "SearchFilters":
        """Filter samt den Angaben aus dem Suchtext (die gehen vor)."""
        ops = query.operators
        merged = self.model_copy()
        if ops.languages:
            merged.languages = ops.languages
        if ops.channel:
            merged.channel = ops.channel
        if ops.min_seconds is not None or ops.max_seconds is not None:
            merged.length, merged.min_seconds, merged.max_seconds = None, ops.min_seconds, ops.max_seconds
        if ops.year_from is not None or ops.year_to is not None:
            merged.period, merged.year_from, merged.year_to = None, ops.year_from, ops.year_to
        if ops.location:
            merged.location = ops.location
        return merged

    def seconds(self) -> tuple[Optional[int], Optional[int]]:
        if self.min_seconds is not None or self.max_seconds is not None:
            return self.min_seconds, self.max_seconds
        return LENGTHS[self.length] if self.length else (None, None)

    @property
    def feed_applies(self) -> bool:
        """Noch nicht geladene Feed-Einträge passen nur, wenn Ort und Stand sie zulassen."""
        return self.location is None and self.state in (None, "new")


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _common(f: SearchFilters, *, duration: str, date: str, lang: str, channel: str,
            with_language: bool) -> tuple[list[str], list]:
    """Gemeinsame Bedingungen für Videos und Feed-Einträge."""
    conditions, params = [], []
    if with_language and f.languages:
        sql, codes = language.filter_sql(lang, f.languages)
        conditions.append(sql)
        params.extend(codes)
    low, high = f.seconds()
    if low:
        conditions.append(f"COALESCE({duration}, 0) >= ?")
        params.append(low)
    if high is not None:
        conditions.append(f"COALESCE({duration}, 0) < ?")
        params.append(high)
    if f.period:
        conditions.append(f"{date} >= datetime('now', ?)")
        params.append(f"-{PERIOD_DAYS[f.period]} days")
    if f.year_from is not None:
        conditions.append(f"CAST(strftime('%Y', {date}) AS INTEGER) >= ?")
        params.append(f.year_from)
    if f.year_to is not None:
        conditions.append(f"CAST(strftime('%Y', {date}) AS INTEGER) <= ?")
        params.append(f.year_to)
    if f.channel:
        conditions.append(f"{channel} LIKE ? ESCAPE '\\'")
        params.append(_like(f.channel))
    return conditions, params


def video_sql(f: SearchFilters, alias: str = "v", *, shorts_excluded: bool,
              with_language: bool = True) -> tuple[str, list]:
    """WHERE-Baustein für fertige Videos (Bibliothek, Archiv, eigene)."""
    conditions = [f"{alias}.status = 'ready'"]
    if shorts_excluded:
        conditions.append(f"COALESCE({alias}.video_type, 'video') <> 'short'")
    more, params = _common(f, duration=f"{alias}.duration", date=f"{alias}.upload_date",
                           lang=f"{alias}.language", channel=f"{alias}.channel_name", with_language=with_language)
    conditions.extend(more)
    if f.location == "bibliothek":
        conditions.append(f"COALESCE({alias}.is_archived, 0) = 0")
    elif f.location == "archiv":
        conditions.append(f"COALESCE({alias}.is_archived, 0) = 1")
    elif f.location == "eigene":
        conditions.append(f"{alias}.source IN ('local', 'imported')")
    if f.state:
        conditions.append(f"{watch_state.state_sql(alias)} = ?")
        params.append(f.state)
    if f.since:
        conditions.append(f"{alias}.download_date > ?")
        params.append(f.since)
    return " AND ".join(conditions), params


def feed_sql(f: SearchFilters, alias: str = "r", channel_alias: str = "s", *, shorts_excluded: bool,
             with_language: bool = True) -> tuple[str, list]:
    """WHERE-Baustein für Feed-Einträge, die noch nicht fertig geladen sind
    (nicht ausgeblendet; ausgeblendete hat der Nutzer abgelehnt)."""
    conditions = [f"COALESCE({alias}.dismissed, 0) = 0",
                  f"COALESCE({alias}.feed_status, 'active') <> 'dismissed'",
                  f"NOT EXISTS (SELECT 1 FROM videos lv WHERE lv.id = {alias}.video_id AND lv.status = 'ready')"]
    if shorts_excluded:
        conditions.append(f"COALESCE({alias}.video_type, 'video') <> 'short'")
    more, params = _common(f, duration=f"{alias}.duration", date=f"{alias}.published",
                           lang=f"{alias}.language", channel=f"{channel_alias}.channel_name",
                           with_language=with_language)
    conditions.extend(more)
    if f.since:
        conditions.append(f"{alias}.created_at > ?")
        params.append(f.since)
    return " AND ".join(conditions), params


# Ordnung außer "passend" (die bestimmt jede Quelle selbst)
VIDEO_ORDER = {
    "neu": "v.upload_date DESC, v.id", "alt": "v.upload_date ASC, v.id",
    "lang": "v.duration DESC, v.id", "kurz": "COALESCE(v.duration, 0) ASC, v.id",
    "aufrufe": "COALESCE(v.view_count, 0) DESC, v.id",
}
FEED_ORDER = {
    "neu": "r.published DESC, r.id", "alt": "r.published ASC, r.id",
    "lang": "r.duration DESC, r.id", "kurz": "COALESCE(r.duration, 0) ASC, r.id",
    "aufrufe": "COALESCE(r.views, 0) DESC, r.id",
}
