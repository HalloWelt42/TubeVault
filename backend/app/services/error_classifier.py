"""
Error Classifier v1.0.0

Reine Klassifizierungs-Logik für Download-Fehler. Keine Side-Effects.
Extrahiert aus download_service._process damit Tests ohne I/O möglich sind.

Kategorien (mutually exclusive, Reihenfolge = Prioritaet):
  members_only : Early-Access/Paid Content → 1d/7d retry_wait
  unavailable  : private/removed/copyright → parken, kein Retry
  bot          : Bot-Detection             → hartes 1h-Cooldown
  throttle     : Rate-Limit, 429, 403      → exponential backoff
  temporary    : 5xx, timeout, reset       → exponential backoff
  unknown      : alles andere              → Standard-Retry
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorClass:
    """Klassifikations-Ergebnis. Genau EINES der Flags ist True (außer unknown)."""
    members_only: bool = False
    unavailable: bool = False
    bot: bool = False
    throttle: bool = False
    temporary: bool = False

    @property
    def unknown(self) -> bool:
        return not (self.members_only or self.unavailable or self.bot
                    or self.throttle or self.temporary)

    @property
    def is_retryable(self) -> bool:
        """Soll der Queue-Worker einen automatischen Retry versuchen?"""
        return self.throttle or self.temporary or self.bot or self.members_only

    @property
    def is_terminal(self) -> bool:
        """Soll der Job sofort geparkt werden (kein sinnvoller Retry)?"""
        return self.unavailable


_MEMBERS_ONLY_KW = (
    "join this channel",
    "members-only",
    "members on level",      # Early-Access Variante
    "channel's members",
)

_UNAVAILABLE_KW = (
    "video unavailable",
    "private video",
    "removed",
    "account terminated",      # "Account terminated"
    "has been terminated",     # "This account has been terminated" (YT-Standard)
    "copyright",
    "not available",
    "age-restricted",
    "sign in to confirm your age",
)

_BOT_KW = (
    "detected as a bot",
    "do not open an issue",
)

_THROTTLE_KW = (
    "retries exceeded",
    "429",
    "too many requests",
    "throttl",
    "rate limit",
    "forbidden",
)

_TEMPORARY_KW = (
    "503",
    "service unavailable",
    "temporarily unavailable",
    "http error 5",
    "server error",
    "connection reset",
    "timed out",
    "timeout",
)


def classify(err: str) -> ErrorClass:
    """Download-Fehler-String in Kategorie einordnen.

    Priorität (wichtig wegen Überschneidungen):
    1. members_only hat Vorrang vor unavailable (z.B. 'not available' ist in beiden)
    2. bot hat Vorrang vor throttle (beide können 'forbidden' enthalten)
    3. throttle hat Vorrang vor temporary (429 vor 503)

    Rueckgabe hat stets genau EINE True-Flag (oder alle False = unknown).
    """
    if not err:
        return ErrorClass()
    low = err.lower()

    # 1. members_only (hat Vorrang - ueberschneidet sich mit "not available")
    if any(kw in low for kw in _MEMBERS_ONLY_KW):
        return ErrorClass(members_only=True)

    # 2. unavailable (andere dauerhafte Fehler)
    if any(kw in low for kw in _UNAVAILABLE_KW):
        return ErrorClass(unavailable=True)

    # 3. bot (hat Vorrang vor throttle – beide koennen 'forbidden' enthalten)
    if any(kw in low for kw in _BOT_KW):
        return ErrorClass(bot=True)

    # 4. throttle (429, rate limit, generisch forbidden)
    if any(kw in low for kw in _THROTTLE_KW):
        return ErrorClass(throttle=True)

    # 5. temporary (5xx, Netzwerk)
    if any(kw in low for kw in _TEMPORARY_KW):
        return ErrorClass(temporary=True)

    return ErrorClass()
