"""
Throttle-Berechnungs-Logic (pure, keine I/O).

Entscheidet welcher ratelimit-Wert (bytes/sec) an yt-dlp übergeben wird,
basierend auf Settings + Video-Metadaten.

Modi:
  realtime : ratelimit = filesize / duration * 1.2
  fixed    : ratelimit = kbps * 1024
  off / 0  : kein ratelimit

Separates Modul, damit Tests ohne sqlite/yt-dlp-I/O möglich sind.
"""
from dataclasses import dataclass


# Minimum realtime-Rate, damit sehr kurze Videos nicht auf <32 KB/s fallen.
# (Ein 30s-Video mit 1 MB wäre sonst 33 KB/s – yt-dlp Overhead braucht mehr.)
_MIN_REALTIME_BYTES_S = 32 * 1024

# Overhead-Faktor bei Realtime: Download sollte 20% schneller als Wiedergabe
# sein, damit Merge-Zeit + Buffer nicht zum Engpass werden.
_REALTIME_OVERHEAD = 1.2


@dataclass(frozen=True)
class ThrottleDecision:
    """Ergebnis der Throttle-Berechnung."""
    # yt-dlp ratelimit-Wert (bytes/sec). 0 = kein Limit.
    bytes_per_sec: int = 0
    # Menschenlesbare Begründung (für Logs/UI).
    reason: str = "off"

    @property
    def kbps(self) -> int:
        return self.bytes_per_sec // 1024 if self.bytes_per_sec else 0

    @property
    def active(self) -> bool:
        return self.bytes_per_sec > 0


def compute(
    *,
    realtime: bool,
    fixed_kbps: int,
    duration_s: int | float | None,
    filesize_bytes: int | float | None,
    tbr_kbps: int | float | None = None,
) -> ThrottleDecision:
    """Berechnet den effektiven ratelimit.

    Args:
        realtime: True = dynamisch aus Video-Metadaten, False = fester Wert
        fixed_kbps: fester Wert in KB/s (nur genutzt wenn realtime=False)
        duration_s: Video-Dauer in Sekunden (realtime-Mode)
        filesize_bytes: Dateigröße in Bytes (realtime-Mode, primär)
        tbr_kbps: yt-dlp 'tbr' in kbit/s (realtime-Fallback wenn filesize fehlt)

    Returns:
        ThrottleDecision mit bytes_per_sec + reason.

    Invariante:
        - realtime=True + kein duration → fallback auf fixed_kbps, sonst off
        - realtime=False + fixed_kbps<=0 → off
    """
    if realtime:
        # duration konvertieren (yt-dlp kann String oder Zahl liefern)
        dur = _safe_float(duration_s)
        size = _safe_float(filesize_bytes)

        # Fallback über tbr × duration wenn filesize fehlt
        if not size and dur and tbr_kbps:
            tbr = _safe_float(tbr_kbps)
            if tbr:
                size = tbr * 1000 / 8 * dur

        if dur and size:
            rate = int(size / dur * _REALTIME_OVERHEAD)
            rate = max(_MIN_REALTIME_BYTES_S, rate)
            return ThrottleDecision(bytes_per_sec=rate, reason="realtime")

        # Realtime gewünscht, aber Metadaten fehlen → nehme fixed_kbps als Fallback
        # (wenn user einen gesetzt hat) oder bleibt off.
        if fixed_kbps > 0:
            return ThrottleDecision(
                bytes_per_sec=fixed_kbps * 1024,
                reason="fixed_fallback",
            )
        return ThrottleDecision(reason="realtime_no_metadata")

    # Fester KB/s-Wert
    if fixed_kbps and fixed_kbps > 0:
        return ThrottleDecision(
            bytes_per_sec=fixed_kbps * 1024,
            reason="fixed",
        )

    return ThrottleDecision(reason="off")


def _safe_float(v) -> float:
    """Tolerante Umwandlung: None/leer/non-numeric → 0.0."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
