"""
TubeVault - Sprache: Kürzel, Namen, Flaggen, Herkunft, Vorrang

Die eine Stelle für alles, was eine Sprachangabe bedeutet (Wunsch 15.10.2026:
Sprache als durchgängiger Aspekt, filtern und suchen, kleine Labels mit
Flagge). Hier steht nur Wissen, kein Datenbankzugriff - Einstellungs-Schema,
Erkennung (language_detect) und Zuordnung (language_assign) bauen darauf auf.

Kürzel: ISO 639-1 in Kleinbuchstaben ("en-US", "eng", "iw" werden zu "en",
"en", "he"). Unbekanntes gilt als keine Angabe - lieber unbekannt als falsch.

Herkunft einer Angabe und ihr Vorrang (stärkste zuerst):
  hand        vom Nutzer gesetzt - keine Automatik ändert das je
  quelle      Angabe der Quelle beim Laden (Sprache der Original-Tonspur)
  untertitel  Sprache der Untertitel bzw. des Transkripts (gesprochen)
  text        aus Titel und Beschreibung erkannt (ab gemessener Sicherheit)
  kanal       Sprache des Kanals, nur wenn der Kanal eindeutig ist
"""
import re
from typing import Mapping, NamedTuple, Optional

from app.models.language import LanguageCatalog, LanguageCount, LanguageInfo, LanguageSourceInfo

# ─── Herkunft und Vorrang ─────────────────────────────────────────────

HAND = "hand"
QUELLE = "quelle"
UNTERTITEL = "untertitel"
TEXT = "text"
KANAL = "kanal"

# Höherer Rang gewinnt; gleicher Rang ersetzt (neuere Angabe derselben Art)
RANK: dict[str, int] = {KANAL: 1, TEXT: 2, UNTERTITEL: 3, QUELLE: 4, HAND: 5}

SOURCE_LABELS: dict[str, str] = {
    HAND: "von Hand",
    QUELLE: "Angabe beim Laden",
    UNTERTITEL: "Untertitel oder Transkript",
    TEXT: "erkannt aus Titel und Beschreibung",
    KANAL: "Sprache des Kanals",
}

# Herkünfte, die die GESPROCHENE Sprache belegen. Nur sie dürfen der
# Spracherkennung (KI-Transkript) vorgegeben werden - ein deutscher Titel
# über englischem Ton würde sonst ins Deutsche gezwungen.
SPOKEN = frozenset({HAND, QUELLE, UNTERTITEL})

# Herkünfte, die sich lokal nicht wiederholen lassen: sie bleiben bei einer
# Neubewertung stehen, bis Stärkeres kommt
_NOT_DERIVABLE = (HAND, QUELLE)

# Stand der Regeln (Erkennung, Schwellen, Vorrang). Erhöhen, wenn sich etwas
# daran ändert: der Hintergrundlauf bewertet dann den ganzen Bestand neu.
RULES_VERSION = 1

# ─── Kanalsprache ─────────────────────────────────────────────────────

# Gemessen an 1.556 Videos mit Angabe der Quelle (jedes Video gegen die
# übrigen seines Kanals): ab 3 bekannten Videos und 90 % Anteil stimmt die
# Kanalmehrheit in 97,9 % (Abdeckung 80,7 %); bei 80 % Anteil nur 97,3 %.
CHANNEL_MIN_KNOWN = 3
CHANNEL_MIN_SHARE = 0.9

MIXED = "mul"      # Kanal mit mehreren Sprachen (ISO 639-2 "mehrere")
UNKNOWN = "und"    # Filter und Zähler: ohne Sprachangabe (ISO 639-2 "unbestimmt")

# ─── Sprachen ─────────────────────────────────────────────────────────


class LanguageDef(NamedTuple):
    code: str                       # ISO 639-1
    name: str                       # deutscher Name
    region: Optional[str] = None    # Land der Flagge (ISO 3166-1), None = keine passende
    aliases: tuple[str, ...] = ()   # ISO 639-2/3 und alte Kürzel


# Flaggen: das Land, mit dem man die Sprache gemeinhin verbindet (Englisch GB,
# Portugiesisch PT, Arabisch SA). Ohne eindeutiges Land keine Flagge.
LANGUAGES: tuple[LanguageDef, ...] = (
    LanguageDef("de", "Deutsch", "DE", ("deu", "ger")),
    LanguageDef("en", "Englisch", "GB", ("eng",)),
    LanguageDef("fr", "Französisch", "FR", ("fra", "fre")),
    LanguageDef("es", "Spanisch", "ES", ("spa",)),
    LanguageDef("it", "Italienisch", "IT", ("ita",)),
    LanguageDef("pl", "Polnisch", "PL", ("pol",)),
    LanguageDef("ru", "Russisch", "RU", ("rus",)),
    LanguageDef("uk", "Ukrainisch", "UA", ("ukr",)),
    LanguageDef("pt", "Portugiesisch", "PT", ("por",)),
    LanguageDef("nl", "Niederländisch", "NL", ("nld", "dut")),
    LanguageDef("ja", "Japanisch", "JP", ("jpn",)),
    LanguageDef("zh", "Chinesisch", "CN", ("zho", "chi", "cmn")),
    LanguageDef("tr", "Türkisch", "TR", ("tur",)),
    LanguageDef("ar", "Arabisch", "SA", ("ara",)),
    LanguageDef("hi", "Hindi", "IN", ("hin",)),
    LanguageDef("ko", "Koreanisch", "KR", ("kor",)),
    LanguageDef("sv", "Schwedisch", "SE", ("swe",)),
    LanguageDef("da", "Dänisch", "DK", ("dan",)),
    LanguageDef("no", "Norwegisch", "NO", ("nor", "nob", "nno", "nb", "nn")),
    LanguageDef("fi", "Finnisch", "FI", ("fin",)),
    LanguageDef("cs", "Tschechisch", "CZ", ("ces", "cze")),
    LanguageDef("el", "Griechisch", "GR", ("ell", "gre")),
    LanguageDef("he", "Hebräisch", "IL", ("heb", "iw")),
    LanguageDef("hu", "Ungarisch", "HU", ("hun",)),
    LanguageDef("ro", "Rumänisch", "RO", ("ron", "rum", "mo")),
    LanguageDef("bg", "Bulgarisch", "BG", ("bul",)),
    LanguageDef("hr", "Kroatisch", "HR", ("hrv",)),
    LanguageDef("sr", "Serbisch", "RS", ("srp",)),
    LanguageDef("bs", "Bosnisch", "BA", ("bos",)),
    LanguageDef("sk", "Slowakisch", "SK", ("slk", "slo")),
    LanguageDef("sl", "Slowenisch", "SI", ("slv",)),
    LanguageDef("et", "Estnisch", "EE", ("est",)),
    LanguageDef("lv", "Lettisch", "LV", ("lav",)),
    LanguageDef("lt", "Litauisch", "LT", ("lit",)),
    LanguageDef("is", "Isländisch", "IS", ("isl", "ice")),
    LanguageDef("ga", "Irisch", "IE", ("gle",)),
    LanguageDef("lb", "Luxemburgisch", "LU", ("ltz",)),
    LanguageDef("mt", "Maltesisch", "MT", ("mlt",)),
    LanguageDef("sq", "Albanisch", "AL", ("sqi", "alb")),
    LanguageDef("mk", "Mazedonisch", "MK", ("mkd", "mac")),
    LanguageDef("be", "Belarussisch", "BY", ("bel",)),
    LanguageDef("ka", "Georgisch", "GE", ("kat", "geo")),
    LanguageDef("hy", "Armenisch", "AM", ("hye", "arm")),
    LanguageDef("az", "Aserbaidschanisch", "AZ", ("aze",)),
    LanguageDef("kk", "Kasachisch", "KZ", ("kaz",)),
    LanguageDef("fa", "Persisch", "IR", ("fas", "per")),
    LanguageDef("ur", "Urdu", "PK", ("urd",)),
    LanguageDef("bn", "Bengalisch", "BD", ("ben",)),
    LanguageDef("pa", "Panjabi", "IN", ("pan",)),
    LanguageDef("mr", "Marathi", "IN", ("mar",)),
    LanguageDef("ta", "Tamil", "IN", ("tam",)),
    LanguageDef("te", "Telugu", "IN", ("tel",)),
    LanguageDef("ne", "Nepalesisch", "NP", ("nep",)),
    LanguageDef("th", "Thailändisch", "TH", ("tha",)),
    LanguageDef("vi", "Vietnamesisch", "VN", ("vie",)),
    LanguageDef("id", "Indonesisch", "ID", ("ind", "in")),
    LanguageDef("ms", "Malaiisch", "MY", ("msa", "may")),
    LanguageDef("tl", "Tagalog", "PH", ("tgl", "fil")),
    LanguageDef("sw", "Suaheli", "TZ", ("swa",)),
    LanguageDef("af", "Afrikaans", "ZA", ("afr",)),
    LanguageDef("ca", "Katalanisch", "AD", ("cat",)),
    LanguageDef("eu", "Baskisch", None, ("eus", "baq")),
    LanguageDef("gl", "Galicisch", None, ("glg",)),
    LanguageDef("cy", "Walisisch", None, ("cym", "wel")),
    LanguageDef("la", "Latein", "VA", ("lat",)),
    LanguageDef("eo", "Esperanto", None, ("epo",)),
    LanguageDef("yi", "Jiddisch", None, ("yid", "ji")),
)

BY_CODE: dict[str, LanguageDef] = {lang.code: lang for lang in LANGUAGES}
_ALIASES: dict[str, str] = {alias: lang.code for lang in LANGUAGES for alias in lang.aliases}
_SEPARATOR = re.compile(r"[-_\s]")


def normalize(raw) -> Optional[str]:
    """Beliebige Sprachangabe auf das Kürzel bringen ("en-US" -> "en",
    "deu" -> "de"). Unbekanntes, "und", "zxx" und Leeres ergeben None."""
    text = str(raw or "").strip().lower()
    if not text:
        return None
    primary = _SEPARATOR.split(text, maxsplit=1)[0]
    code = _ALIASES.get(primary, primary)
    return code if code in BY_CODE else None


def from_user(raw) -> Optional[str]:
    """Sprache, wie man sie tippt: Kürzel ("en", "eng") oder deutscher Name
    ("englisch", "Deutsch"). Unbekanntes ergibt None."""
    code = normalize(raw)
    if code:
        return code
    text = str(raw or "").strip().lower()
    return next((lang.code for lang in LANGUAGES if lang.name.lower() == text), None)


def name(code: Optional[str]) -> str:
    """Deutscher Name ("Englisch"); Unbekanntes als Kürzel in Großbuchstaben."""
    if code == MIXED:
        return "Gemischt"
    if code in (None, "", UNKNOWN):
        return "Unbekannt"
    known = BY_CODE.get(code)
    return known.name if known else str(code).upper()


def flag(code: Optional[str]) -> Optional[str]:
    """Flaggen-Zeichen der Sprache (Englisch: GB) oder None."""
    known = BY_CODE.get(code or "")
    if not known or not known.region:
        return None
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in known.region)


def source_label(source: Optional[str]) -> Optional[str]:
    return SOURCE_LABELS.get(source or "")


# ─── Vorrang ──────────────────────────────────────────────────────────


class Assignment(NamedTuple):
    """Sprache und ihre Herkunft; beides None = unbekannt."""
    code: Optional[str]
    source: Optional[str]


NONE = Assignment(None, None)


def rank(source: Optional[str]) -> int:
    return RANK.get(source or "", 0)


def may_replace(current_source: Optional[str], new_source: str) -> bool:
    """Darf eine Angabe der Herkunft new_source die bestehende ersetzen?
    Die Wahl des Nutzers ersetzt nur der Nutzer; sonst gewinnt die stärkere
    oder gleich starke Herkunft."""
    if new_source == HAND:
        return True
    if current_source == HAND:
        return False
    return rank(new_source) >= rank(current_source)


def decide(current: Assignment, evidence: Mapping[str, Optional[str]]) -> Assignment:
    """Sprache aus allen Hinweisen wählen. evidence: Herkunft -> Kürzel der
    lokal ableitbaren Hinweise (untertitel, text, kanal, bei Feed-Einträgen
    auch die Angabe am geladenen Video). Was sich lokal nicht wiederholen
    lässt (von Hand, Angabe beim Laden), bleibt stehen, bis Stärkeres kommt."""
    if current.source == HAND and current.code:
        return current
    candidates = {source: code for source, code in evidence.items() if code and source in RANK}
    if current.code and current.source in _NOT_DERIVABLE:
        candidates.setdefault(current.source, current.code)
    if not candidates:
        return NONE
    best = max(candidates, key=rank)
    return Assignment(candidates[best], best)


def channel_language(counts: Mapping[str, int]) -> Optional[str]:
    """Sprache eines Kanals aus der Zahl seiner Videos je Sprache (ohne die,
    die selbst nur die Kanalsprache tragen): die Mehrheit ab Mindestanteil,
    sonst gemischt; bei zu wenigen bekannten Videos unbekannt."""
    known = {code: count for code, count in counts.items() if code and code in BY_CODE and count > 0}
    total = sum(known.values())
    if total < CHANNEL_MIN_KNOWN:
        return None
    top = max(known, key=lambda code: known[code])
    return top if known[top] / total >= CHANNEL_MIN_SHARE else MIXED


def catalog() -> LanguageCatalog:
    """Katalog für die Oberfläche: Namen, Flaggen, Herkünfte."""
    return LanguageCatalog(
        languages=[LanguageInfo(code=lang.code, name=lang.name, flag=flag(lang.code)) for lang in LANGUAGES],
        sources=[LanguageSourceInfo(key=key, label=label, rank=rank(key)) for key, label in SOURCE_LABELS.items()],
        unknown=LanguageInfo(code=UNKNOWN, name=name(UNKNOWN)),
        mixed=LanguageInfo(code=MIXED, name=name(MIXED)),
    )


# ─── Filter und Zähler ────────────────────────────────────────────────


def parse_filter(values) -> list[str]:
    """Filterwerte ("en,fr", auch mehrfach) zu bekannten Kürzeln; "und" steht
    für ohne Sprache, "mul" für gemischte Kanäle. Unbekanntes fällt weg."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip().lower()
            code = part if part in (UNKNOWN, MIXED) else normalize(part)
            if code and code not in out:
                out.append(code)
    return out


def code_sql(column: str) -> str:
    """Sprache einer Spalte für Zähler: ohne Angabe zählt als "und"."""
    return f"COALESCE(NULLIF({column}, ''), '{UNKNOWN}')"


def filter_sql(column: str, codes: list[str]) -> tuple[str, list[str]]:
    """WHERE-Baustein "Sprache ist eine von codes" (Ergebnis von parse_filter)."""
    marks = ",".join("?" * len(codes))
    return f"{code_sql(column)} IN ({marks})", list(codes)


def counts_from_rows(rows) -> list[LanguageCount]:
    """Zeilen (code, count) zu Zählern, häufigste zuerst, ohne Sprache zuletzt."""
    counts = [LanguageCount(code=row[0], count=row[1]) for row in rows if row[0] and row[1]]
    return sorted(counts, key=lambda item: (item.code == UNKNOWN, -item.count, name(item.code)))
