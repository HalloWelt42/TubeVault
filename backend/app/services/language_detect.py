"""
TubeVault - Sprache aus Titel und Beschreibung erkennen

Rein lokal mit py3langid (reines Python auf numpy, Modell im Paket, keine
Abrufe). Gewählt nach Messung an 1.556 Videos mit Angabe der Quelle und
1.500 ohne (Prüfung 15.10.2026, beschränkt auf DETECTABLE):

                     Titel und Beschreibung        nur Titel        je Text
    py3langid        97,3 % Abdeckung, 97,6 %   58,6 %, 96,8 %     0,1 ms
    lingua (hoch)    97,2 %, 97,5 %              42,9 %, 97,5 %    1,1 ms, Paket 300 MB
    langdetect       98,3 %, 97,3 %              83,9 %, 93,1 %    1,4 ms, Ergebnis schwankt
    fast-langdetect  69,7 %, 97,3 %              55,2 %, 97,1 %    0,04 ms
    (Abdeckung und Genauigkeit bei Sicherheit 0,9)

Fast alle verbleibenden "Fehler" sind Videos, deren Text in einer anderen
Sprache steht als der Ton (deutsche Titel über englischem Ton und umgekehrt):
darin stimmten alle vier Erkenner überein. Ohne diese 34 Videos liegt
py3langid bei 99,9 %. Auf dem Pi (ARM64, Linux) lädt das Modell in 0,45 s
und belegt etwa 70 MB; ein Text kostet 0,09 ms.

Schwelle: Sicherheit ab 0,95 und mindestens 3 Wörter. Damit Titel und
Beschreibung 96,4 % Abdeckung bei 97,7 % Übereinstimmung mit der Tonspur,
nur Titel 49,5 % bei 97,3 % - darunter lieber keine Angabe als eine falsche.
"""
import re
import threading
from typing import Iterable, Optional

from pydantic import BaseModel

from app.services import language

# Sprachen, zwischen denen die Erkennung wählt (gemessen mit genau dieser
# Auswahl). Kleiner als der Katalog: seltene Sprachen werden sonst bei kurzen
# Titeln öfter fälschlich getroffen.
DETECTABLE = ("de", "en", "fr", "es", "it", "pl", "ru", "uk", "pt", "nl", "ja", "zh", "tr", "ar", "hi",
              "ko", "sv", "da", "no", "fi", "cs", "el", "he", "hu", "ro")
MIN_CONFIDENCE = 0.95
MIN_WORDS = 3
# Gemessen wurde mit den ersten 600 Zeichen der Beschreibung; mehr ändert
# das Ergebnis kaum und kostet nur Zeit
DESCRIPTION_CHARS = 600

_URL = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
_HANDLE = re.compile(r"[#@]\w+")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[^\W\d_]{2,}")


class Detection(BaseModel):
    code: str
    confidence: float


def clean_text(title: Optional[str], description: Optional[str]) -> str:
    """Erkennbarer Text: Titel und Beschreibungsanfang ohne Adressen,
    Schlagwörter (#...), Namen (@...) und Zeitmarken."""
    text = f"{title or ''}\n{(description or '')[:DESCRIPTION_CHARS]}"
    for pattern in (_URL, _HANDLE, _TIME):
        text = pattern.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


_lock = threading.Lock()
_identifier = None


def _model():
    """Das Modell beim ersten Bedarf laden (einmal, auch aus mehreren Threads)."""
    global _identifier
    if _identifier is None:
        with _lock:
            if _identifier is None:
                from py3langid.langid import MODEL_FILE, LanguageIdentifier
                identifier = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
                identifier.set_languages(list(DETECTABLE))
                _identifier = identifier
    return _identifier


def detect(title: Optional[str], description: Optional[str] = None) -> Optional[Detection]:
    """Sprache des Textes, nur wenn sie sicher genug ist (sonst None).
    Rechnet auf der CPU - aus asyncio heraus über asyncio.to_thread."""
    text = clean_text(title, description)
    if len(_WORD.findall(text)) < MIN_WORDS:
        return None
    code, confidence = _model().classify(text)
    code = language.normalize(code)
    if not code or confidence < MIN_CONFIDENCE:
        return None
    return Detection(code=code, confidence=round(float(confidence), 4))


def detect_many(texts: Iterable[tuple[Optional[str], Optional[str]]]) -> list[Optional[Detection]]:
    """Mehrere (Titel, Beschreibung) auf einmal - ein Thread-Wechsel je Portion."""
    return [detect(title, description) for title, description in texts]
