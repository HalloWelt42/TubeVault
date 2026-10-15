"""
Wörter vergleichen wie der Volltextindex (klein, ohne Akzente) und
Textausschnitte um eine Fundstelle bilden.

Die Oberfläche hebt Treffer nach derselben Regel hervor
(frontend/src/lib/utils/searchHighlight.js): ein Wort trifft, wenn es mit
dem Suchwort beginnt (Wortanfang) bzw. ihm gleicht (kurze Wörter, Wortfolgen).
"""
import re
import unicodedata

WORD = re.compile(r"\w+", re.UNICODE)
ELLIPSIS = "..."
# Wortanfänge und Teilwörter zählen erst ab so vielen Zeichen
PREFIX_MIN = 4


def fold(text: str) -> str:
    """Klein und ohne Akzente ("Löten" -> "loten"), wie der Index vergleicht."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def word_hits(token: str, word: str, prefix: bool) -> bool:
    """Trifft ein Wort des Textes das Suchwort? Beide ungefaltet übergeben."""
    folded, wanted = fold(token), fold(word)
    return folded.startswith(wanted) if prefix else folded == wanted


def first_hit(text: str, terms: list) -> int | None:
    """Position (Zeichen) des ersten Wortes, das einen Suchbegriff trifft.
    terms: query.Term (words, prefix); bei Wortfolgen zählt das erste Wort."""
    tokens = list(WORD.finditer(text or ""))
    for index, token in enumerate(tokens):
        for term in terms:
            words = term.words
            if index + len(words) > len(tokens):
                continue
            last = len(words) - 1
            if all(word_hits(tokens[index + i].group(), word, term.prefix and i == last)
                   for i, word in enumerate(words)):
                return token.start()
    return None


def excerpt(text: str, terms: list, width: int = 240) -> str:
    """Ausschnitt von etwa width Zeichen um die erste Fundstelle, an
    Wortgrenzen geschnitten; ohne Fundstelle der Anfang."""
    text = " ".join((text or "").split())
    if len(text) <= width:
        return text
    hit = first_hit(text, terms)
    start = 0 if hit is None else max(0, hit - width // 3)
    end = min(len(text), start + width)
    start = max(0, end - width)
    if start > 0:
        space = text.find(" ", start)
        start = space + 1 if 0 <= space < start + 30 else start
    if end < len(text):
        space = text.rfind(" ", start, end)
        end = space if space > start + width // 2 else end
    return f"{ELLIPSIS if start > 0 else ''}{text[start:end].strip()}{ELLIPSIS if end < len(text) else ''}"


def _term_in(term, folded: str, tokens: list[str]) -> bool:
    """Steckt ein Suchbegriff in einem (gefalteten) Text? Lange Einzelwörter
    auch mitten im Wort ("bank" in "Werkbank"), kurze nur ganz, Wortfolgen
    Wort für Wort hintereinander."""
    words = [fold(word) for word in term.words]
    if len(words) == 1 and not term.phrase:
        return words[0] in folded if len(words[0]) >= PREFIX_MIN else words[0] in tokens
    last = len(words) - 1
    for start in range(len(tokens) - last):
        if all(tokens[start + i] == word or (i == last and term.prefix and tokens[start + i].startswith(word))
               for i, word in enumerate(words)):
            return True
    return False


# Felder eines Eintrags, vorbereitet: Name -> (gefalteter Text, gefaltete Wörter)
Prepared = dict[str, tuple[str, list[str]]]


def prepare(fields: dict[str, str]) -> Prepared:
    return {name: (fold(text or ""), [fold(t) for t in WORD.findall(text or "")]) for name, text in fields.items()}


def prepared_matching(prepared: Prepared, query) -> list[str] | None:
    """Für kleine Bestände (Kanäle, Playlists) ohne eigenen Index: passt die
    Suche, wenn jede Gruppe in einem der Felder steckt und kein
    ausgeschlossener Begriff vorkommt. Ergebnis: die Felder mit Treffern,
    None ohne Treffer."""
    hit_fields: list[str] = []
    for group in query.groups:
        found = [name for name, (folded, tokens) in prepared.items()
                 if any(_term_in(term, folded, tokens) for term in group)]
        if not found:
            return None
        hit_fields.extend(name for name in found if name not in hit_fields)
    if any(_term_in(term, folded, tokens) for term in query.excluded for folded, tokens in prepared.values()):
        return None
    return hit_fields or None
