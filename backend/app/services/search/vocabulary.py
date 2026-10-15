"""
Wortschatz aus Titeln (Videos, Kapitel, Feed) und Kanalnamen: ergänzt das
angefangene Wort beim Tippen und schlägt bei Tippfehlern ein bekanntes Wort
vor ("kernfusoin" -> "kernfusion").

Gezählt wird, wie oft ein Wort vorkommt; Wörter, die nur einmal vorkommen,
fallen weg (meist Tippfehler oder Kennungen). Der Wortschatz entsteht beim
ersten Bedarf in einem eigenen Thread und wird nach VOCABULARY_TTL_S im
Hintergrund erneuert; bis dahin gilt der alte.
"""
import asyncio
import bisect
import logging
import time
from collections import Counter, defaultdict
from typing import Optional

from app.database import db
from app.services.search.query import Query
from app.services.search.text import PREFIX_MIN, WORD, fold

logger = logging.getLogger(__name__)

VOCABULARY_TTL_S = 30 * 60
MIN_COUNT = 2                 # seltener vorkommende Wörter zählen nicht
MIN_LENGTH = 3
COMPLETE_FROM = 2             # ab so vielen Zeichen wird ergänzt

_SOURCES = (
    "SELECT title FROM videos WHERE status = 'ready'",
    "SELECT channel_name FROM videos WHERE status = 'ready'",
    "SELECT title FROM chapters",
    "SELECT title FROM rss_entries",
    "SELECT channel_name FROM subscriptions",
)


class Vocabulary:
    def __init__(self, counts: Counter):
        forms: dict[str, Counter] = defaultdict(Counter)
        for word, count in counts.items():
            forms[fold(word)][word] += count
        self.count: dict[str, int] = {}
        self.form: dict[str, str] = {}
        for key, variants in forms.items():
            total = sum(variants.values())
            if total >= MIN_COUNT:
                self.count[key] = total
                self.form[key] = variants.most_common(1)[0][0]
        self.keys = sorted(self.count)
        self.by_initial: dict[str, list[str]] = defaultdict(list)
        for key in self.keys:
            self.by_initial[key[0]].append(key)

    def starting_with(self, prefix: str, limit: int) -> list[str]:
        """Bekannte Wörter mit diesem Anfang, häufigste zuerst (Schreibweise wie meist im Titel)."""
        start = bisect.bisect_left(self.keys, prefix)
        end = bisect.bisect_left(self.keys, prefix + "￿")
        best = sorted(self.keys[start:end], key=lambda key: -self.count[key])[:limit]
        return [self.form[key] for key in best]

    def known(self, word: str, prefix: bool) -> bool:
        key = fold(word)
        if key in self.count:
            return True
        if not prefix:
            return False
        position = bisect.bisect_left(self.keys, key)
        return position < len(self.keys) and self.keys[position].startswith(key)

    def closest(self, word: str) -> Optional[str]:
        """Ähnlichstes bekanntes Wort (Tippfehler), sonst None."""
        key = fold(word)
        limit = 1 if len(key) <= 5 else 2
        best: Optional[tuple[int, int, str]] = None
        for candidate in self.by_initial.get(key[0], []):
            if abs(len(candidate) - len(key)) > limit:
                continue
            distance = _distance(key, candidate, limit)
            if distance <= limit:
                rank = (distance, -self.count[candidate], candidate)
                best = rank if best is None or rank < best else best
        return self.form[best[2]] if best else None


def _distance(a: str, b: str, limit: int) -> int:
    """Tippabstand (Einfügen, Löschen, Ersetzen, Vertauschen); bricht über limit ab."""
    previous_previous: list[int] = []
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, char_b in enumerate(b, 1):
            cost = 0 if char_a == char_b else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and char_a == b[j - 2] and a[i - 2] == char_b:
                current[j] = min(current[j], previous_previous[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        previous_previous, previous = previous, current
    return previous[-1]


def build(texts: list[str]) -> Vocabulary:
    counts: Counter = Counter()
    for text in texts:
        counts.update(word.lower() for word in WORD.findall(text or "")
                      if len(word) >= MIN_LENGTH and not word.isdigit())
    return Vocabulary(counts)


_current: Optional[Vocabulary] = None
_built_at = 0.0
_lock = asyncio.Lock()


async def _texts() -> list[str]:
    texts: list[str] = []
    for sql in _SOURCES:
        texts.extend(row[0] for row in await db.fetch_all(sql) if row[0])
    return texts


async def _rebuild() -> None:
    global _current, _built_at
    async with _lock:
        if _current is not None and time.monotonic() - _built_at < VOCABULARY_TTL_S:
            return
        started = time.monotonic()
        _current = await asyncio.to_thread(build, await _texts())
        _built_at = time.monotonic()
        logger.info(f"[SUCHE] Wortschatz: {len(_current.keys)} Wörter in {_built_at - started:.1f} s")


async def current() -> Vocabulary:
    """Der Wortschatz; beim ersten Mal wird gewartet, später im Hintergrund erneuert."""
    if _current is None:
        await _rebuild()
    elif time.monotonic() - _built_at >= VOCABULARY_TTL_S and not _lock.locked():
        asyncio.create_task(_rebuild())
    return _current


def reset() -> None:
    """Für Tests: Wortschatz verwerfen."""
    global _current, _built_at
    _current, _built_at = None, 0.0


async def complete(text: str, limit: int = 6) -> list[str]:
    """Ergänzungen für das zuletzt getippte Wort, samt dem Text davor."""
    if not text or text[-1].isspace():
        return []
    words = WORD.findall(text)
    if not words or not text.rstrip().endswith(words[-1]) or len(words[-1]) < COMPLETE_FROM:
        return []
    last = words[-1]
    head = text[: len(text.rstrip()) - len(last)]
    vocabulary = await current()
    return [f"{head}{word}" for word in vocabulary.starting_with(fold(last), limit + 1)
            if fold(word) != fold(last)][:limit]


async def did_you_mean(query: Query) -> Optional[str]:
    """Suchtext mit korrigierten Wörtern oder None, wenn nichts zu verbessern ist."""
    vocabulary = await current()
    text, changed = query.text, False
    for term in query.terms:
        if term.phrase or len(term.words) != 1 or len(fold(term.words[0])) < PREFIX_MIN:
            continue
        word = term.words[0]
        if vocabulary.known(word, term.prefix):
            continue
        better = vocabulary.closest(word)
        if not better:
            continue
        position = text.lower().find(word)
        if position >= 0:
            text = text[:position] + better + text[position + len(word):]
            changed = True
    return text if changed else None
