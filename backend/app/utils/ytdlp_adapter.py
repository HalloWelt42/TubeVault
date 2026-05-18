"""
TubeVault – yt-dlp Adapter v1.3.0
v1.3.0: exportiert aktuell gewählten Throttle-Wert (für Live-Anzeige im UI)
Stellt pytubefix-kompatible Objekte bereit, die intern yt-dlp nutzen.

Damit können alle bestehenden Call-Sites (yt.title, yt.streams, yt.chapters,
yt.captions, Channel.videos, Playlist.videos, Search.videos etc.) unverändert
bleiben, während der Daten-Backend auf yt-dlp umschaltet.

Nicht abgedeckt (bewusst nicht als Adapter):
- stream.download() — Downloads laufen besser direkt über yt-dlp (siehe
  download_service Umstellung in Schritt 5). Stream.url bleibt verfügbar
  für direkten Download-Zugriff.
"""
from __future__ import annotations

import logging
import re
from functools import cached_property
from typing import Iterator, Optional
from urllib.parse import urlparse, parse_qs

import yt_dlp

logger = logging.getLogger(__name__)

# Live-Throttle: KB/s des aktuell laufenden Downloads (0 = kein Limit).
# Wird vom ytdlp-Adapter pro Download gesetzt und vom download_service
# für den WebSocket-Broadcast (Live-Anzeige im UI) ausgelesen.
_CURRENT_THROTTLE_KBPS: int = 0

def get_current_throttle_kbps() -> int:
    return _CURRENT_THROTTLE_KBPS

def _set_current_throttle_kbps(v: int):
    global _CURRENT_THROTTLE_KBPS
    _CURRENT_THROTTLE_KBPS = int(v or 0)


# bgutil-PO-Token-Provider läuft als Docker-Service 'tubevault-pot:4416'
# Override per ENV möglich (z.B. in docker-compose)
import os as _os
import random as _random
_POT_BASE_URL = _os.getenv("POT_PROVIDER_URL", "http://tubevault-pot:4416")


# ──────────────────────────────────────────────────────────────────
# Anti-Bot: Player-Client- und User-Agent-Rotation
# ──────────────────────────────────────────────────────────────────
# Player-Clients aus yt-dlp 2026.x – Pool für Zufalls-Rotation.
# Sortiert grob nach "least-detected": tv-Family braucht keinen PO-Token,
# mediaconnect ist intern, ios/android sind weniger aggressiv geprüft.
# 'default' (= web) ist als Fallback dabei, aber nicht primär.
_PLAYER_CLIENT_POOL = [
    ["tv", "default"],
    ["tv_simply", "tv"],
    ["mediaconnect", "tv"],
    ["ios", "tv"],
    ["android_music", "tv"],
    ["mweb", "tv"],
    ["web_safari", "tv"],
    ["default", "tv"],
]

# Echte User-Agents (Stand 2026, breit gestreut). yt-dlp setzt sonst
# einen erkennbar einheitlichen UA → durch Rotation wirken Calls
# weniger nach "ein einzelner Client hämmert dauernd".
_USER_AGENT_POOL = [
    # Chrome Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    # Firefox Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Safari Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    # Mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
]


def _pick_player_clients(exclude: list[list[str]] | None = None) -> list[str]:
    """Zufälliger Player-Client-Stack für einen Call. Erste Wahl wechselt,
    'tv' bleibt als robuster Fallback meist dabei.

    exclude: bereits versuchte Stacks (Liste von Listen) – beim Retry
    übergeben damit nicht der gleiche Client zweimal hintereinander kommt.
    Wenn alle Pool-Einträge durch sind, fällt die Funktion auf Random zurück.
    """
    pool = _PLAYER_CLIENT_POOL
    if exclude:
        excluded = {tuple(e) for e in exclude}
        remaining = [p for p in pool if tuple(p) not in excluded]
        if remaining:
            return list(_random.choice(remaining))
    return list(_random.choice(pool))


def _pick_user_agent() -> str:
    return _random.choice(_USER_AGENT_POOL)


# Desktop-only UAs (kein Mobile/iPhone/Android). Wichtig für YouTube-
# Channel-Tabs: ein Mobile-UA triggert die mobile Web-Seite, die der
# youtube:tab-Extractor nicht parsen kann ("Unable to recognize tab page").
_DESKTOP_UA_POOL = [
    ua for ua in _USER_AGENT_POOL
    if "Mobile" not in ua and "iPhone" not in ua and "Android" not in ua
]


def _pick_desktop_user_agent() -> str:
    return _random.choice(_DESKTOP_UA_POOL or _USER_AGENT_POOL)


def _ua_short(ua: str) -> str:
    """Kurzform für Logs – z.B. 'Chrome/132 Win10', 'Firefox/131 Linux',
    'Safari/18 macOS', 'iPhone iOS18'."""
    s = ua.lower()
    if "iphone" in s: return "iPhone"
    if "android" in s: return "Android"
    if "firefox" in s and "linux" in s: return "Firefox-Linux"
    if "firefox" in s: return "Firefox-Win"
    if "safari" in s and "chrome" not in s: return "Safari-Mac"
    if "macintosh" in s and "chrome" in s: return "Chrome-Mac"
    if "windows" in s and "chrome" in s: return "Chrome-Win"
    if "linux" in s and "chrome" in s: return "Chrome-Linux"
    return "Other"


def _strategy_for_call(label: str = "") -> tuple[list[str], str]:
    """Wählt zufälligen Client+UA, loggt kompakt auf DEBUG für Diagnose.
    label kann z.B. die video_id sein, damit man im Log nachverfolgen kann."""
    clients = _pick_player_clients()
    ua = _pick_user_agent()
    cf = _cookiefile()
    logger.debug(
        f"[YTBOT] {label} client={'+'.join(clients)} ua={_ua_short(ua)} "
        f"cookies={'yes' if cf else 'no'}"
    )
    return clients, ua

# Zwei Cookie-Files mit klarer Rollenverteilung:
# - cookies.txt        → ANON (visitor-only). Wird IMMER mitgeschickt, hilft
#                        gegen einfache Bot-Detection ohne Account-Risiko.
# - cookies-login.txt  → LOGIN (echte YouTube-Session). Wird NUR als
#                        Eskalation eingesetzt – bei BOT-DETECTION oder
#                        AGE-GATE im Retry. So brennen wir den Account
#                        nicht in jedem Request.
def _cookiefile() -> str | None:
    """Anonyme Cookies. Default-Pfad."""
    p = "/app/config/cookies.txt"
    return p if _os.path.isfile(p) and _os.path.getsize(p) > 0 else None


def _login_cookiefile() -> str | None:
    """Login-Cookies. Optional, wird nur bei Härtefällen eingesetzt."""
    p = "/app/config/cookies-login.txt"
    return p if _os.path.isfile(p) and _os.path.getsize(p) > 0 else None


# Einmal beim Import loggen: ist POT-Provider erreichbar? sind Cookies da?
def _log_bot_setup():
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"{_POT_BASE_URL}/ping", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            import json as _j
            data = _j.loads(r.read().decode("utf-8", errors="replace"))
            logger.info(f"[BOT-SETUP] POT-Provider erreichbar: v{data.get('version')} "
                        f"(uptime={int(data.get('server_uptime', 0))}s)")
    except Exception as e:
        logger.warning(f"[BOT-SETUP] POT-Provider NICHT erreichbar ({_POT_BASE_URL}): {e}")
    import time as _time
    def _describe(path: str) -> str:
        sz = _os.path.getsize(path)
        age_s = int(_time.time() - _os.path.getmtime(path))
        if age_s < 3600:
            age_str = f"{age_s // 60}min"
        elif age_s < 86400:
            age_str = f"{age_s // 3600}h"
        else:
            age_str = f"{age_s // 86400}d"
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                yt = sum(1 for ln in f if ln and not ln.startswith("#") and ".youtube.com" in ln)
        except Exception:
            yt = -1
        return f"{path} ({sz} Bytes, {yt} YT-Cookies, alter={age_str})"

    cf = _cookiefile()
    if cf:
        logger.info(f"[BOT-SETUP] cookies.txt (anon) aktiv: {_describe(cf)}")
    else:
        logger.info("[BOT-SETUP] cookies.txt fehlt – nur Random-Strategie ohne Cookies")
    lf = _login_cookiefile()
    if lf:
        logger.info(f"[BOT-SETUP] cookies-login.txt verfügbar (Eskalation): {_describe(lf)}")
    else:
        logger.info("[BOT-SETUP] cookies-login.txt nicht da – BOT-Härtefälle bleiben unlösbar")

_log_bot_setup()

def _build_ydl_opts(label: str = "", *, for_download: bool = False,
                    use_login_cookies: bool = False) -> dict:
    """Baut yt-dlp-Optionen MIT zufälliger Anti-Bot-Strategie pro Call.
    Player-Client & User-Agent werden randomisiert, POT-Provider + EJS bleiben fix.

    use_login_cookies=True schaltet von der ANON-cookies.txt auf die
    LOGIN-cookies-login.txt um. Wird nur in Härtefällen (Retry mit
    BOT-DETECTION oder AGE-GATE) eingeschaltet, damit der Account nicht
    in jedem Request mitläuft.
    """
    clients, ua = _strategy_for_call(label)
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "extractor_args": {
            "youtube": {
                "player_client": clients,
            },
            "youtubepot-bgutilhttp": {
                "base_url": [_POT_BASE_URL],
            },
        },
        "remote_components": ["ejs:github"],
        "http_headers": {
            "User-Agent": ua,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        },
    }
    if not for_download:
        opts["skip_download"] = True
    cf = _login_cookiefile() if use_login_cookies else _cookiefile()
    if use_login_cookies and not cf:
        # Fallback: wenn Login-Cookies fehlen, wenigstens anon nehmen
        cf = _cookiefile()
    if cf:
        opts["cookiefile"] = cf
    return opts


def _classify_yt_error(msg: str) -> str:
    """Grob-Kategorie aus Fehlermeldung – für Logs / spätere Statistik."""
    if not msg:
        return "unknown"
    s = msg.lower()
    if "sign in to confirm you" in s and "bot" in s: return "BOT-DETECTION"
    if "sign in to confirm your age" in s: return "AGE-GATE"
    if "members-only" in s or "members on level" in s or "join this channel" in s: return "MEMBERS-ONLY"
    if "private video" in s: return "PRIVATE"
    # GEO-BLOCKED: spezifischer als UNAVAILABLE matchen. Permanent –
    # Retry mit anderem Player-Client ändert die IP-Geolocation nicht.
    if ("not made this video available in your country" in s
        or "not available in your country" in s
        or "blocked it on copyright grounds in your country" in s):
        return "GEO-BLOCKED"
    # LIVE-COMING: kein Fehler im engeren Sinn – Stream startet noch.
    # Verdient retry_wait (1h), nicht parked.
    if "live event will begin" in s or "premieres in" in s:
        return "LIVE-COMING"
    # FORMAT-MISMATCH spezifisch (vor UNAVAILABLE matchen, weil "not available"
    # auch in der format-Meldung vorkommt). Tritt auf wenn ein fester itag
    # vom Resolve mit dem gewählten Player-Client im Download nicht passt.
    if "requested format is not available" in s: return "FORMAT-MISMATCH"
    if "this video has been removed" in s or "video has been removed" in s: return "REMOVED"
    if "video unavailable" in s or "not available" in s: return "UNAVAILABLE"
    if "removed" in s: return "REMOVED"
    if "copyright" in s: return "COPYRIGHT"
    if "http error 429" in s or "too many requests" in s: return "RATE-429"
    if "http error 4" in s: return "HTTP-4xx"
    if "http error 5" in s: return "HTTP-5xx"
    if "timeout" in s or "timed out" in s: return "TIMEOUT"
    return "OTHER"


# Wirklich permanente Fehler – kein Login der Welt löst die.
# GEO-BLOCKED: Region-Sperre, Player-Client-Wechsel hilft nicht.
_PERMANENT_CATEGORIES = {"PRIVATE", "REMOVED", "COPYRIGHT", "GEO-BLOCKED"}
# Brauchen Login-Cookies um lösbar zu sein. Ohne cookies-login.txt
# sind sie effektiv permanent. Mit Login + Mitgliedschaft kommen sie durch.
_NEEDS_LOGIN = {"AGE-GATE", "MEMBERS-ONLY"}
_MAX_RETRIES = 3               # → 4 Versuche total


def _should_retry(cat: str) -> bool:
    """Wahr wenn eine andere Strategie eine Chance hätte.
    - PRIVATE/REMOVED/COPYRIGHT → permanent, False
    - AGE-GATE/MEMBERS-ONLY → nur mit cookies-login.txt sinnvoll
    - alles andere (BOT-DETECTION, RATE-429, HTTP-x, TIMEOUT, FORMAT-MISMATCH, OTHER) → True
    """
    if cat in _PERMANENT_CATEGORIES:
        return False
    if cat in _NEEDS_LOGIN:
        return _login_cookiefile() is not None
    return True


def _needs_login_escalation(cat: str) -> bool:
    """True wenn dieser Fehler-Typ Login-Cookies als Retry-Eskalation braucht.
    BOT-DETECTION + AGE-GATE + MEMBERS-ONLY sind alles 'login-erforderlich'-Fälle
    aus YouTube-Sicht (\"Sign in to confirm\", \"Join this channel\")."""
    return cat in {"BOT-DETECTION", "AGE-GATE", "MEMBERS-ONLY"} and _login_cookiefile() is not None


# ──────────────────────────────────────────────────────────────────
# Permanent-Fail-Cache
# ──────────────────────────────────────────────────────────────────
# Wenn ein Video gerade als MEMBERS-ONLY/PRIVATE/REMOVED erkannt wurde,
# rufen wir innerhalb der nächsten 60 Sekunden NICHT nochmal YouTube an.
# Schützt gegen die typischen 2–3 Folge-Calls aus download_service-Phasen
# (resolve → metadata → download), die sonst alle den gleichen Permanent-
# Fehler nochmal in den Logs würfeln und Rate-Budget verschwenden.
import time as _time_module
_PERMANENT_FAIL_CACHE: dict[str, tuple[float, str]] = {}
_PERMANENT_CACHE_TTL = 60.0  # Sekunden
_PERMANENT_CACHE_MAX = 500


def _cache_check(video_id: str) -> str | None:
    """Wenn das Video kürzlich permanent fehlgeschlagen ist: gib die alte
    Fehlermeldung zurück, damit Caller sofort raisen kann ohne YouTube-Call."""
    if not video_id or len(video_id) != 11:
        return None
    entry = _PERMANENT_FAIL_CACHE.get(video_id)
    if not entry:
        return None
    ts, msg = entry
    if _time_module.time() - ts > _PERMANENT_CACHE_TTL:
        _PERMANENT_FAIL_CACHE.pop(video_id, None)
        return None
    return msg


def _cache_mark(video_id: str, msg: str):
    """Markiere ein Video als permanent fehlgeschlagen (TTL 60s)."""
    if not video_id or len(video_id) != 11:
        return
    _PERMANENT_FAIL_CACHE[video_id] = (_time_module.time(), msg)
    # Cache nicht unbegrenzt wachsen lassen
    if len(_PERMANENT_FAIL_CACHE) > _PERMANENT_CACHE_MAX:
        cutoff = _time_module.time() - _PERMANENT_CACHE_TTL
        for k in [k for k, v in _PERMANENT_FAIL_CACHE.items() if v[0] < cutoff]:
            _PERMANENT_FAIL_CACHE.pop(k, None)


def _cache_clear():
    """Tests / manuelle Resets."""
    _PERMANENT_FAIL_CACHE.clear()


# ──────────────────────────────────────────────────────────────────
# Retry-Progress-Hook (Live-Sichtbarkeit der Versuche im UI)
# ──────────────────────────────────────────────────────────────────
# Caller (download_service) registriert einen Callback, der bei jedem
# Retry-Versuch synchron aufgerufen wird. So kann der Job-Status im UI
# zwischen den yt-dlp-Versuchen aktualisiert werden, statt erst am Ende.
_RETRY_HOOK = None  # type: Optional[callable]


def set_retry_hook(hook):
    """Setzt globalen Hook fn(label: str, attempt: int, total: int, cat: str, msg: str).
    Wird bei jedem failed Versuch aufgerufen, BEVOR der nächste startet.
    Ausnahmen aus dem Hook werden geschluckt – Hook darf den Adapter nicht stören."""
    global _RETRY_HOOK
    _RETRY_HOOK = hook


def _fire_retry_hook(label: str, attempt: int, total: int, cat: str, msg: str):
    h = _RETRY_HOOK
    if h is None:
        return
    try:
        h(label, attempt, total, cat, msg)
    except Exception:
        pass


def _pytubefix_extract_fallback(url: str, label: str) -> Optional[dict]:
    """3. Stufe: pytubefix als komplett alternative Implementation. Anderer
    Code-Pfad, andere YouTube-Endpoints – kann manchmal liefern wo yt-dlp
    blockt (oder umgekehrt). Liefert ein yt-dlp-kompatibles Info-Dict
    (best-effort) oder None bei Fehler.

    Wird nur aufgerufen wenn alle yt-dlp-Versuche scheitern UND der Fehler
    nicht permanent (Members/Private/...) ist – sonst wäre es Verschwendung.
    """
    try:
        from app.utils.pytube_client import make_youtube
        yt = make_youtube(url)
        # Minimal-Schema, das die meisten Caller-Sites erwarten:
        info = {
            "id": getattr(yt, "video_id", None) or label,
            "title": getattr(yt, "title", None) or "",
            "description": getattr(yt, "description", None) or "",
            "duration": getattr(yt, "length", None) or 0,
            "channel": getattr(yt, "author", None) or "",
            "channel_id": getattr(yt, "channel_id", None) or "",
            "view_count": getattr(yt, "views", None) or 0,
            "thumbnail": getattr(yt, "thumbnail_url", None) or "",
            "webpage_url": url,
            "extractor": "pytubefix-fallback",
            "_pytubefix_obj": yt,  # Roh-Objekt für Caller die mehr brauchen
        }
        # Streams als pytubefix-StreamQuery; Caller können die direkt nehmen
        try:
            info["_pytubefix_streams"] = list(yt.streams)
        except Exception:
            info["_pytubefix_streams"] = []
        logger.info(
            f"[YTBOT-FALLBACK] {label} pytubefix lieferte info "
            f"(streams={len(info.get('_pytubefix_streams') or [])})"
        )
        return info
    except Exception as e:
        logger.warning(f"[YTBOT-FALLBACK-FAIL] {label} pytubefix: {str(e)[:160]}")
        return None


def _ydl_extract(url: str, extra_opts: Optional[dict] = None,
                 force_clients: Optional[list[str]] = None,
                 desktop_ua_only: bool = False) -> dict:
    """Zentraler yt-dlp Extract-Call mit Random Anti-Bot-Strategie + Auto-Retry.
    Bei BOT-DETECTION oder AGE-GATE wird im Retry auf cookies-login.txt
    eskaliert (falls vorhanden), damit echte Auth-Cookies gegen Härtefälle
    helfen ohne den Account in jedem normalen Call zu brennen.

    force_clients:    feste player_client-Liste statt Random-Pool. Für
                      Channel-/Playlist-Listings (youtube:tab), die mit
                      'web' zuverlässig parsen – kein Rotations-Vorteil dort.
    desktop_ua_only:  nur Desktop-User-Agents (kein Mobile). Mobile-UA
                      triggert die mobile Web-Seite, die youtube:tab nicht
                      parsen kann ("Unable to recognize tab page").
    Beide Defaults = altes Verhalten → Stream-Download-Pfad unverändert."""
    label = url.rsplit("v=", 1)[-1][:11] if "v=" in url else url[-32:]
    # Permanent-Fail-Cache: spart die typischen 2-3 Folge-Calls aus den
    # download_service-Phasen für ein Video, das gerade als Members-Only/
    # Private/etc. erkannt wurde.
    cached = _cache_check(label)
    if cached:
        logger.debug(f"[YTBOT-CACHE-HIT] {label} permanent-fail cache: {cached[:80]}")
        raise yt_dlp.utils.DownloadError(cached)
    tried_clients: list[list[str]] = []
    last_exc: Optional[Exception] = None
    use_login = False
    import time as _t

    for attempt in range(_MAX_RETRIES + 1):
        if force_clients:
            clients = list(force_clients)        # fix, keine Rotation
        else:
            clients = _pick_player_clients(exclude=tried_clients)
        ua = _pick_desktop_user_agent() if desktop_ua_only else _pick_user_agent()
        tried_clients.append(clients)
        opts = _build_ydl_opts(label=label, use_login_cookies=use_login)
        opts["extractor_args"]["youtube"]["player_client"] = clients
        opts["http_headers"]["User-Agent"] = ua
        if extra_opts:
            opts.update(extra_opts)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=False)
            if use_login:
                logger.info(f"[YTBOT-OK] {label} via Login-Cookies-Eskalation")
            return result
        except Exception as e:
            last_exc = e
            cat = _classify_yt_error(str(e))
            cookie_mode = "login" if use_login else "anon"
            logger.warning(
                f"[YTBOT-FAIL] {label} cat={cat} client={'+'.join(clients)} "
                f"ua={_ua_short(ua)} cookies={cookie_mode} "
                f"attempt={attempt + 1}/{_MAX_RETRIES + 1} err={str(e)[:160]}"
            )
            if not _should_retry(cat) or attempt >= _MAX_RETRIES:
                # Permanente Fehler kurz cachen, damit Folge-Phasen aus
                # download_service nicht denselben YouTube-Call nochmal machen
                if cat in _PERMANENT_CATEGORIES:
                    _cache_mark(label, str(e)[:200])
                raise
            # Eskalation: Login-Cookies aktivieren ab jetzt, falls sinnvoll
            if not use_login and _needs_login_escalation(cat):
                use_login = True
                logger.info(
                    f"[YTBOT-ESCALATE] {label} cat={cat} → schalte auf "
                    f"cookies-login.txt für Folgeversuche"
                )
            backoff = 0 if cat == "BOT-DETECTION" else (3 * (attempt + 1))
            logger.info(
                f"[YTBOT-RETRY] {label} cat={cat} cookies={'login' if use_login else 'anon'} "
                f"next_attempt={attempt + 2}/{_MAX_RETRIES + 1} sleep={backoff}s"
            )
            _fire_retry_hook(label, attempt + 2, _MAX_RETRIES + 1, cat,
                             f"Versuch {attempt + 2}/{_MAX_RETRIES + 1} ({cat})")
            if backoff:
                _t.sleep(backoff)
    # Alle yt-dlp-Versuche scheiterten. Letzte Stufe: pytubefix als komplett
    # andere Implementation (nur wenn Fehler nicht permanent war – sonst
    # bringt's nichts).
    if last_exc:
        last_cat = _classify_yt_error(str(last_exc))
        if last_cat not in _PERMANENT_CATEGORIES and last_cat != "AGE-GATE":
            logger.info(f"[YTBOT-FALLBACK-START] {label} alle yt-dlp gescheitert (cat={last_cat}) → pytubefix")
            fallback = _pytubefix_extract_fallback(url, label)
            if fallback is not None:
                return fallback
        raise last_exc
    raise RuntimeError("ydl_extract: alle Versuche scheiterten ohne Exception")


def _vtt_to_srt(vtt_text: str) -> str:
    """Minimal-Konverter WebVTT → SRT."""
    lines = vtt_text.splitlines()
    # WEBVTT-Header + Metadaten-Blöcke entfernen
    out_blocks: list[list[str]] = []
    current: list[str] = []
    seen_header = False
    for line in lines:
        if not seen_header:
            if line.strip().startswith("WEBVTT"):
                seen_header = True
            continue
        if "-->" in line:
            # Zeitformat VTT → SRT (Punkt → Komma)
            line = line.replace(".", ",")
            # Cue-Settings (nach zweitem Timestamp) abschneiden
            m = re.match(r"^(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)", line)
            if m:
                current = [f"{m.group(1)} --> {m.group(2)}"]
                continue
            m2 = re.match(r"^(\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d,\d\d\d)", line)
            if m2:
                current = [f"00:{m2.group(1)} --> 00:{m2.group(2)}"]
                continue
            current = [line]
        elif line.strip() == "":
            if current:
                out_blocks.append(current)
                current = []
        else:
            if current:
                current.append(line)
    if current:
        out_blocks.append(current)

    srt = []
    for idx, block in enumerate(out_blocks, start=1):
        if not block:
            continue
        srt.append(str(idx))
        srt.extend(block)
        srt.append("")
    return "\n".join(srt).strip() + "\n"


# ═══════════════════════════════════════════════════════════════════
#  STREAM + STREAM-QUERY
# ═══════════════════════════════════════════════════════════════════

class StreamAdapter:
    """pytubefix.Stream-kompatibel."""

    __slots__ = ("_fmt", "_on_progress", "_watch_url", "_video_duration")

    def __init__(self, fmt: dict, on_progress_callback=None, watch_url: str = "", video_duration: int = 0):
        self._fmt = fmt
        self._video_duration = video_duration
        self._on_progress = on_progress_callback
        self._watch_url = watch_url

    @property
    def itag(self) -> str:
        return str(self._fmt.get("format_id", ""))

    @property
    def mime_type(self) -> str:
        ext = self._fmt.get("ext", "")
        vc = self._fmt.get("vcodec", "none")
        ac = self._fmt.get("acodec", "none")
        if vc != "none":
            return f"video/{ext}"
        if ac != "none":
            return f"audio/{ext}"
        return f"application/{ext}"

    @property
    def subtype(self) -> str:
        return self._fmt.get("ext", "")

    @property
    def type(self) -> str:
        if self._fmt.get("vcodec", "none") != "none":
            return "video"
        if self._fmt.get("acodec", "none") != "none":
            return "audio"
        return "other"

    @property
    def is_progressive(self) -> bool:
        return self._fmt.get("vcodec", "none") != "none" and self._fmt.get("acodec", "none") != "none"

    @property
    def is_adaptive(self) -> bool:
        return not self.is_progressive and (
            self._fmt.get("vcodec", "none") != "none" or self._fmt.get("acodec", "none") != "none"
        )

    @property
    def includes_audio_track(self) -> bool:
        return self._fmt.get("acodec", "none") != "none"

    @property
    def includes_video_track(self) -> bool:
        return self._fmt.get("vcodec", "none") != "none"

    @property
    def resolution(self) -> Optional[str]:
        # pytubefix-kompatibel: "720p" statt "1280x720"
        h = self._fmt.get("height")
        if h:
            return f"{h}p"
        return None

    @property
    def abr(self) -> Optional[str]:
        a = self._fmt.get("abr")
        if a:
            return f"{int(a)}kbps"
        return None

    @property
    def filesize(self) -> int:
        return self._fmt.get("filesize") or self._fmt.get("filesize_approx") or 0

    @property
    def url(self) -> str:
        return self._fmt.get("url", "")

    @property
    def fps(self) -> Optional[int]:
        return self._fmt.get("fps")

    @property
    def codecs(self) -> list[str]:
        """Liste der Codecs analog pytubefix (z.B. ['avc1.640028', 'mp4a.40.2'])."""
        out = []
        vc = self._fmt.get("vcodec")
        if vc and vc != "none":
            out.append(vc)
        ac = self._fmt.get("acodec")
        if ac and ac != "none":
            out.append(ac)
        return out

    def download(
        self,
        output_path: Optional[str] = None,
        filename: Optional[str] = None,
        filename_prefix: Optional[str] = None,
        skip_existing: bool = False,
        timeout: Optional[int] = None,
        max_retries: int = 0,
    ) -> str:
        """Download via yt-dlp (nicht httpx!) — YouTube-Throttling wird intern behandelt.
        Ruft on_progress_callback(stream, chunk, remaining) analog pytubefix.
        """
        import os as _os
        from pathlib import Path as _Path
        import yt_dlp as _ydl

        out_dir = _Path(output_path) if output_path else _Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"stream_{self.itag}.{self.subtype or 'bin'}"
        if filename_prefix:
            fname = f"{filename_prefix}{fname}"

        # yt-dlp hängt den echten Container-Ext aus dem Format an — wir strippen unseren eigenen,
        # damit keine Doppelungen wie "audio_tmp.m4a.m4a" entstehen.
        fname_base, _fname_ext = _os.path.splitext(fname)
        out_tmpl = str(out_dir / f"{fname_base}.%(ext)s")

        if skip_existing:
            # Trivial-Check: gibt es schon was passendes?
            existing = list(out_dir.glob(f"{fname_base}.*"))
            if existing and existing[0].stat().st_size > 0:
                return str(existing[0])

        cb = self._on_progress
        this = self
        final_path = {"path": None}

        def _hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                if total and total != this._fmt.get("filesize"):
                    this._fmt["filesize"] = total
                if cb and total:
                    try:
                        cb(this, b"", max(0, total - done))
                    except Exception:
                        pass
            elif status == "finished":
                final_path["path"] = d.get("filename") or d.get("info_dict", {}).get("filepath")
                if cb:
                    total = d.get("total_bytes") or this.filesize
                    if total:
                        this._fmt["filesize"] = total
                    try:
                        cb(this, b"", 0)
                    except Exception:
                        pass

        url = self._watch_url or self._fmt.get("webpage_url")
        if not url:
            raise RuntimeError("StreamAdapter.download: kein Watch-URL bekannt")

        # Random Anti-Bot-Strategie pro Download (Player-Client + UA + Cookies)
        _vid = url.rsplit("v=", 1)[-1][:11] if "v=" in url else "?"
        _label = f"{_vid}/itag={self.itag}"
        opts = _build_ydl_opts(label=_label, for_download=True)
        opts.update({
            "format": str(self.itag),
            "outtmpl": out_tmpl,
            "progress_hooks": [_hook],
            "retries": max(max_retries, 3),
            "fragment_retries": 10,
            "socket_timeout": timeout or 30,
            "overwrites": True,
            # Kein Post-Processing — wir übernehmen Merge im download_service selbst.
            "postprocessors": [],
        })
        # Throttle-Berechnung via throttle_calc.compute() (pure Funktion, getestet).
        # Liest die 2 Settings direkt aus SQLite (sync, pro Download ok).
        try:
            import sqlite3 as _sq
            from app.config import DB_PATH as _DB
            from app.constants import SettingsKeys as _K
            from app.services.throttle_calc import compute as _throttle_compute
            _c = _sq.connect(str(_DB))
            _rt = _c.execute(
                "SELECT value FROM settings WHERE key=?",
                (_K.DOWNLOAD_THROTTLE_REALTIME,)
            ).fetchone()
            _kb = _c.execute(
                "SELECT value FROM settings WHERE key=?",
                (_K.DOWNLOAD_THROTTLE_KBPS,)
            ).fetchone()
            _c.close()
            realtime = bool(_rt and str(_rt[0]).lower() == 'true')
            fixed_kbps = int(_kb[0]) if _kb and str(_kb[0]).isdigit() else 0

            decision = _throttle_compute(
                realtime=realtime,
                fixed_kbps=fixed_kbps,
                duration_s=self._video_duration or self._fmt.get("duration"),
                filesize_bytes=(self._fmt.get("filesize")
                                or self._fmt.get("filesize_approx")),
                tbr_kbps=self._fmt.get("tbr"),
            )
            if decision.active:
                opts["ratelimit"] = decision.bytes_per_sec
            _set_current_throttle_kbps(decision.kbps)
            logger.info(f"[throttle] applied: {decision.kbps} KB/s ({decision.reason})")
        except Exception as _e:
            logger.warning(f"[throttle] setup failed: {_e}")
        # Auto-Retry mit neuer Random-Strategie + Login-Eskalation bei
        # BOT-DETECTION/AGE-GATE. Bei FORMAT-MISMATCH öffnen wir den
        # format-Selector damit der neue Player-Client einen kompatiblen
        # Stream wählen kann (statt am festen itag zu scheitern).
        last_ratelimit = opts.get("ratelimit")
        tried_clients: list[list[str]] = [
            opts.get("extractor_args", {}).get("youtube", {}).get("player_client", [])
        ]
        last_exc = None
        use_login = False
        format_was_mismatch = False
        import time as _t
        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                clients = _pick_player_clients(exclude=tried_clients)
                ua = _pick_user_agent()
                tried_clients.append(clients)
                opts = _build_ydl_opts(label=_label, for_download=True,
                                       use_login_cookies=use_login)
                opts["extractor_args"]["youtube"]["player_client"] = clients
                opts["http_headers"]["User-Agent"] = ua
                # Format-Selector: wenn vorheriger Versuch FORMAT-MISMATCH war,
                # statt festen itag eine flexible Auswahl. yt-dlp wählt selbst
                # ein kompatibles Format mit dem aktuellen Player-Client.
                if format_was_mismatch:
                    h = self._fmt.get("height") or 1080
                    fmt = (
                        f"{self.itag}/"
                        f"bestvideo[height<={h}]+bestaudio/"
                        f"best[height<={h}]/best"
                    )
                    logger.info(
                        f"[YTBOT-FORMAT-FALLBACK] {_label} öffne format-selector "
                        f"itag={self.itag} → flex (h<={h})"
                    )
                else:
                    fmt = str(self.itag)
                opts.update({
                    "format": fmt,
                    "outtmpl": out_tmpl,
                    "progress_hooks": [_hook],
                    "retries": max(max_retries, 3),
                    "fragment_retries": 10,
                    "socket_timeout": timeout or 30,
                    "overwrites": True,
                    "postprocessors": [],
                })
                if last_ratelimit is not None:
                    opts["ratelimit"] = last_ratelimit
            try:
                with _ydl.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                last_exc = None
                if use_login:
                    logger.info(f"[YTBOT-OK] {_label} via Login-Cookies-Eskalation")
                break
            except Exception as _dl_e:
                last_exc = _dl_e
                clients_used = opts.get("extractor_args", {}).get("youtube", {}).get("player_client") or []
                ua_used = opts.get("http_headers", {}).get("User-Agent", "")
                cat = _classify_yt_error(str(_dl_e))
                cookie_mode = "login" if use_login else "anon"
                logger.warning(
                    f"[YTBOT-FAIL] {_label} cat={cat} client={'+'.join(clients_used)} "
                    f"ua={_ua_short(ua_used)} cookies={cookie_mode} "
                    f"attempt={attempt + 1}/{_MAX_RETRIES + 1} err={str(_dl_e)[:160]}"
                )
                if not _should_retry(cat) or attempt >= _MAX_RETRIES:
                    if cat in _PERMANENT_CATEGORIES:
                        _cache_mark(_label.split("/")[0], str(_dl_e)[:200])
                    raise
                # FORMAT-MISMATCH-Eskalation: nächster Retry mit offenem Selektor
                if cat == "FORMAT-MISMATCH":
                    format_was_mismatch = True
                if not use_login and _needs_login_escalation(cat):
                    use_login = True
                    logger.info(
                        f"[YTBOT-ESCALATE] {_label} cat={cat} → "
                        f"cookies-login.txt für Folgeversuche"
                    )
                backoff = 0 if cat == "BOT-DETECTION" else (3 * (attempt + 1))
                logger.info(
                    f"[YTBOT-RETRY] {_label} cat={cat} "
                    f"cookies={'login' if use_login else 'anon'} "
                    f"next_attempt={attempt + 2}/{_MAX_RETRIES + 1} sleep={backoff}s"
                )
                _fire_retry_hook(_label, attempt + 2, _MAX_RETRIES + 1, cat,
                                 f"Download-Versuch {attempt + 2}/{_MAX_RETRIES + 1} ({cat})")
                if backoff:
                    _t.sleep(backoff)
                continue
        if last_exc is not None:
            raise last_exc

        # Pfad bestimmen: was der Hook gemeldet hat, oder fallback Suchen
        if final_path["path"] and _os.path.exists(final_path["path"]):
            return final_path["path"]
        # Fallback: glob auf unseren Basenamen
        for cand in out_dir.glob(f"{fname_base}.*"):
            if cand.is_file() and cand.stat().st_size > 0:
                return str(cand)
        raise RuntimeError(
            f"StreamAdapter.download: Zieldatei nicht gefunden (outtmpl={out_tmpl})"
        )

    def __repr__(self) -> str:
        return (
            f"<Stream itag={self.itag} type={self.type} "
            f"res={self.resolution} abr={self.abr} progressive={self.is_progressive}>"
        )


class StreamQueryAdapter:
    """pytubefix.StreamQuery-kompatibel."""

    def __init__(self, streams: list[StreamAdapter]):
        self._streams = streams

    def __iter__(self) -> Iterator[StreamAdapter]:
        return iter(self._streams)

    def __len__(self) -> int:
        return len(self._streams)

    def __getitem__(self, i):
        return self._streams[i]

    def filter(
        self,
        *,
        progressive: Optional[bool] = None,
        adaptive: Optional[bool] = None,
        only_audio: Optional[bool] = None,
        only_video: Optional[bool] = None,
        type: Optional[str] = None,
        resolution: Optional[str] = None,
        subtype: Optional[str] = None,
        mime_type: Optional[str] = None,
        abr: Optional[str] = None,
        fps: Optional[int] = None,
    ) -> "StreamQueryAdapter":
        def keep(s: StreamAdapter) -> bool:
            if progressive is True and not s.is_progressive:
                return False
            if progressive is False and s.is_progressive:
                return False
            if adaptive is True and not s.is_adaptive:
                return False
            if adaptive is False and s.is_adaptive:
                return False
            if only_audio is True and (s.includes_video_track or not s.includes_audio_track):
                return False
            if only_video is True and (s.includes_audio_track or not s.includes_video_track):
                return False
            if type and s.type != type:
                return False
            if resolution and s.resolution != resolution:
                return False
            if subtype and s.subtype != subtype:
                return False
            if mime_type and s.mime_type != mime_type:
                return False
            if abr and s.abr != abr:
                return False
            if fps and s.fps != fps:
                return False
            return True

        return StreamQueryAdapter([s for s in self._streams if keep(s)])

    def order_by(self, attr: str) -> "StreamQueryAdapter":
        def key(s: StreamAdapter):
            if attr == "resolution":
                v = s.resolution
                if v and v.endswith("p"):
                    try:
                        return int(v[:-1])
                    except ValueError:
                        return 0
                return 0
            if attr == "abr":
                v = s.abr
                if v and v.endswith("kbps"):
                    try:
                        return int(v[:-4])
                    except ValueError:
                        return 0
                return 0
            if attr == "fps":
                return s.fps or 0
            if attr == "filesize":
                return s.filesize
            return getattr(s, attr, 0) or 0

        return StreamQueryAdapter(sorted(self._streams, key=key))

    def desc(self) -> "StreamQueryAdapter":
        return StreamQueryAdapter(list(reversed(self._streams)))

    def asc(self) -> "StreamQueryAdapter":
        return self

    def first(self) -> Optional[StreamAdapter]:
        return self._streams[0] if self._streams else None

    def last(self) -> Optional[StreamAdapter]:
        return self._streams[-1] if self._streams else None

    def get_by_itag(self, itag) -> Optional[StreamAdapter]:
        itag = str(itag)
        for s in self._streams:
            if s.itag == itag:
                return s
        return None

    def get_audio_only(self, subtype: Optional[str] = None) -> Optional[StreamAdapter]:
        q = self.filter(only_audio=True)
        if subtype:
            q = q.filter(subtype=subtype)
        best = q.order_by("abr").desc().first()
        return best

    def get_highest_resolution(self) -> Optional[StreamAdapter]:
        # Bevorzugt progressiv (kein Merge nötig); sonst höchste adaptive Video-Res
        prog = self.filter(progressive=True).order_by("resolution").desc().first()
        if prog:
            return prog
        return self.filter(only_video=True).order_by("resolution").desc().first()

    def get_lowest_resolution(self) -> Optional[StreamAdapter]:
        return self.filter(progressive=True).order_by("resolution").asc().first()


# ═══════════════════════════════════════════════════════════════════
#  CHAPTER + CAPTION
# ═══════════════════════════════════════════════════════════════════

class ChapterAdapter:
    """pytubefix.Chapter-kompatibel."""

    __slots__ = ("title", "start_seconds", "duration")

    def __init__(self, title: str, start_seconds: int, duration: int):
        self.title = title
        self.start_seconds = start_seconds
        self.duration = duration

    @property
    def end_seconds(self) -> int:
        return self.start_seconds + self.duration


class CaptionAdapter:
    """pytubefix.Caption-kompatibel."""

    def __init__(self, code: str, name: str, url: str, ext: str):
        self.code = code
        self.name = name
        self._url = url
        self._ext = ext

    def generate_srt_captions(self) -> str:
        import httpx
        r = httpx.get(self._url, timeout=20)
        r.raise_for_status()
        text = r.text
        if self._ext in ("vtt", "webvtt"):
            return _vtt_to_srt(text)
        if self._ext == "srt":
            return text
        # Fallback: wenn es wie VTT aussieht, konvertieren; sonst wie es ist
        if text.lstrip().startswith("WEBVTT"):
            return _vtt_to_srt(text)
        return text


# ═══════════════════════════════════════════════════════════════════
#  YOUTUBE (Video)
# ═══════════════════════════════════════════════════════════════════

class YoutubeAdapter:
    """pytubefix.YouTube-kompatibel."""

    def __init__(self, url: str, on_progress_callback=None, **_kwargs):
        self.watch_url = url
        self.video_id = _extract_video_id(url) or ""
        self.on_progress_callback = on_progress_callback
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            self._info = _ydl_extract(self.watch_url)
        return self._info

    # Metadaten
    @property
    def title(self) -> str:
        return self._ensure().get("title") or ""

    @property
    def author(self) -> str:
        return self._ensure().get("uploader") or self._ensure().get("channel") or ""

    @property
    def channel_id(self) -> str:
        return self._ensure().get("channel_id") or ""

    @property
    def channel_url(self) -> str:
        return self._ensure().get("channel_url") or ""

    @property
    def description(self) -> str:
        return self._ensure().get("description") or ""

    @property
    def length(self) -> int:
        return int(self._ensure().get("duration") or 0)

    @property
    def views(self) -> int:
        return int(self._ensure().get("view_count") or 0)

    @property
    def keywords(self) -> list[str]:
        return list(self._ensure().get("tags") or [])

    @property
    def thumbnail_url(self) -> str:
        return self._ensure().get("thumbnail") or ""

    @property
    def publish_date(self):
        import datetime as _dt
        raw = self._ensure().get("upload_date")
        if not raw:
            return None
        try:
            return _dt.datetime.strptime(raw, "%Y%m%d")
        except ValueError:
            return None

    # vid_info-Shim für Altcode, der videoDetails/playabilityStatus liest
    @property
    def vid_info(self) -> dict:
        info = self._ensure()
        is_live = bool(info.get("is_live"))
        was_live = bool(info.get("was_live"))
        return {
            "videoDetails": {
                "videoId": self.video_id,
                "title": info.get("title") or "",
                "author": info.get("uploader") or "",
                "channelId": info.get("channel_id") or "",
                "lengthSeconds": str(info.get("duration") or 0),
                "viewCount": str(info.get("view_count") or 0),
                "shortDescription": info.get("description") or "",
                "keywords": list(info.get("tags") or []),
                "isLive": is_live,
                "isLiveContent": is_live or was_live,
                "isPostLiveDvr": False,
            },
            "playabilityStatus": {
                "status": "OK",
                "playableInEmbed": True,
            },
            # extra für Debug
            "_ytdlp_raw": info,
        }

    # Streams
    @property
    def streams(self) -> StreamQueryAdapter:
        info = self._ensure()
        fmts = info.get("formats") or []
        # Nur Formate mit URL (manche sind nur Platzhalter)
        fmts = [f for f in fmts if f.get("url")]
        # Storyboards/Bilder raus (sb*)
        fmts = [f for f in fmts if f.get("ext") not in ("mhtml",)]
        video_duration = int(info.get("duration") or 0)
        return StreamQueryAdapter([
            StreamAdapter(
                f,
                on_progress_callback=self.on_progress_callback,
                watch_url=self.watch_url,
                video_duration=video_duration,
            )
            for f in fmts
        ])

    # Chapters
    @property
    def chapters(self) -> list[ChapterAdapter]:
        info = self._ensure()
        out: list[ChapterAdapter] = []
        for c in info.get("chapters") or []:
            start = int(c.get("start_time") or 0)
            end = int(c.get("end_time") or start)
            out.append(ChapterAdapter(
                title=c.get("title") or "",
                start_seconds=start,
                duration=max(0, end - start),
            ))
        return out

    # Captions
    @property
    def captions(self) -> list[CaptionAdapter]:
        info = self._ensure()
        out: list[CaptionAdapter] = []
        for lang, variants in (info.get("subtitles") or {}).items():
            fmt = _pick_sub_format(variants)
            if fmt:
                out.append(CaptionAdapter(
                    code=lang,
                    name=fmt.get("name") or lang,
                    url=fmt.get("url"),
                    ext=fmt.get("ext", ""),
                ))
        for lang, variants in (info.get("automatic_captions") or {}).items():
            if lang in (info.get("subtitles") or {}):
                continue  # manuelle haben Vorrang
            fmt = _pick_sub_format(variants)
            if fmt:
                out.append(CaptionAdapter(
                    code=f"a.{lang}",
                    name=fmt.get("name") or f"{lang} (auto)",
                    url=fmt.get("url"),
                    ext=fmt.get("ext", ""),
                ))
        return out


def _pick_sub_format(variants: list[dict]) -> Optional[dict]:
    """Bevorzugte Subtitle-Format-Auswahl: vtt > srt > json3 > srv3 > rest."""
    pref = ["vtt", "srt", "json3", "srv3", "srv2", "srv1"]
    by_ext = {v.get("ext"): v for v in variants if v.get("url")}
    for p in pref:
        if p in by_ext:
            return by_ext[p]
    return next(iter(by_ext.values()), None)


def _extract_video_id(url: str) -> Optional[str]:
    try:
        u = urlparse(url)
        if u.netloc in ("youtu.be",):
            return u.path.lstrip("/").split("/")[0] or None
        if "youtube.com" in u.netloc:
            if u.path == "/watch":
                q = parse_qs(u.query)
                return (q.get("v") or [None])[0]
            if u.path.startswith("/shorts/"):
                return u.path.split("/")[2]
            if u.path.startswith("/embed/") or u.path.startswith("/v/"):
                return u.path.split("/")[2]
    except Exception:
        return None
    # Fallback: direkte ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or ""):
        return url
    return None


# ═══════════════════════════════════════════════════════════════════
#  CHANNEL / PLAYLIST-VIDEO-ITEMS
# ═══════════════════════════════════════════════════════════════════

class ChannelVideoItem:
    """Leichtgewichtiger Video-Eintrag aus einer Channel/Playlist-Liste (flat)."""

    __slots__ = ("video_id", "title", "author", "channel_id", "length",
                 "views", "thumbnail_url", "publish_date", "watch_url")

    def __init__(self, entry: dict, fallback_channel: Optional[dict] = None):
        self.video_id = entry.get("id") or ""
        self.title = entry.get("title") or ""
        self.author = entry.get("uploader") or (fallback_channel or {}).get("channel") or ""
        self.channel_id = entry.get("channel_id") or (fallback_channel or {}).get("channel_id") or ""
        self.length = int(entry.get("duration") or 0)
        self.views = int(entry.get("view_count") or 0)
        thumbs = entry.get("thumbnails") or []
        self.thumbnail_url = (thumbs[-1].get("url") if thumbs else None) or (
            f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg" if self.video_id else ""
        )
        self.publish_date = entry.get("upload_date")
        self.watch_url = entry.get("url") or entry.get("webpage_url") or (
            f"https://www.youtube.com/watch?v={self.video_id}" if self.video_id else ""
        )


# ═══════════════════════════════════════════════════════════════════
#  CHANNEL
# ═══════════════════════════════════════════════════════════════════

class ChannelAdapter:
    """pytubefix.Channel-kompatibel. Lazy; Videos als Generator."""

    def __init__(self, url: str, *, max_videos: Optional[int] = None, **_kwargs):
        self.channel_url = url
        self._max_videos = max_videos
        self._meta: Optional[dict] = None
        # pytubefix-kompatibel: html_url wird vom channel_scanner gesetzt
        # (ch.html_url = ch.videos_url / .shorts_url / .live_url), dann
        # iteriert er ch.url_generator(). Default = Videos-Tab.
        self.html_url: Optional[str] = None

    # ── pytubefix-kompatible Tab-URLs ────────────────────────────────
    @property
    def _base_url(self) -> str:
        """Channel-URL ohne Tab-Suffix."""
        base = self.channel_url.rstrip("/")
        for suffix in ("/videos", "/shorts", "/streams", "/live",
                        "/playlists", "/about", "/featured", "/community"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return base

    @property
    def videos_url(self) -> str:
        return self._base_url + "/videos"

    @property
    def shorts_url(self) -> str:
        return self._base_url + "/shorts"

    @property
    def live_url(self) -> str:
        # YouTube-Tab heißt /streams (pytubefix nennt es live)
        return self._base_url + "/streams"

    def url_generator(self):
        """pytubefix-kompatibel: iteriert ALLE Videos des aktuell via
        html_url gewählten Tabs. yt-dlp paginiert YouTube-Continuations
        automatisch durch – damit kommt der KOMPLETTE Kanal, nicht nur
        die erste Seite. extract_flat hält die Einträge leicht (kein
        volles Video-Objekt → kein OOM wie beim pytubefix-Caching)."""
        tab_url = self.html_url or self.videos_url
        opts = {"extract_flat": "in_playlist"}
        if self._max_videos:
            opts["playlistend"] = self._max_videos
        try:
            # Channel-Tabs: fester web-Client + Desktop-UA. youtube:tab
            # parst damit zuverlässig (Mobile-UA/exotische Clients bringen
            # nur "Unable to recognize tab page" + 4 Fehlversuche).
            info = _ydl_extract(
                tab_url, extra_opts=opts,
                force_clients=["web"], desktop_ua_only=True,
            )
        except Exception as e:
            # Kanal hat diesen Tab evtl. nicht (keine Shorts/Live) → leer
            logger.info(f"ChannelAdapter.url_generator({tab_url}): {str(e)[:140]}")
            return
        fallback = {
            "channel": info.get("channel") or info.get("uploader"),
            "channel_id": info.get("channel_id"),
        }
        entries = info.get("entries") or []
        # Verschachtelung auflösen: Channel-Tab kann eine Liste von
        # Sub-Playlists liefern (z.B. "Videos"-Playlist als ein entry)
        for e in entries:
            if not e:
                continue
            if e.get("_type") == "playlist" and e.get("entries"):
                for sub in e["entries"]:
                    if sub:
                        yield ChannelVideoItem(sub, fallback_channel=fallback)
            else:
                yield ChannelVideoItem(e, fallback_channel=fallback)

    def _ensure_meta(self) -> dict:
        if self._meta is None:
            # Light-Abruf: nur Channel-Grunddaten + flat Video-Liste
            opts = {"extract_flat": "in_playlist"}
            if self._max_videos:
                opts["playlistend"] = self._max_videos
            self._meta = _ydl_extract(
                _channel_videos_url(self.channel_url), extra_opts=opts
            )
        return self._meta

    @property
    def channel_id(self) -> str:
        return self._ensure_meta().get("channel_id") or ""

    @property
    def channel_name(self) -> str:
        return (
            self._ensure_meta().get("channel")
            or self._ensure_meta().get("uploader")
            or self._ensure_meta().get("title")
            or ""
        )

    @property
    def vanity_url(self) -> Optional[str]:
        return self._ensure_meta().get("uploader_url")

    @property
    def thumbnail_url(self) -> str:
        thumbs = self._ensure_meta().get("thumbnails") or []
        return thumbs[-1]["url"] if thumbs else ""

    @property
    def description(self) -> str:
        return self._ensure_meta().get("description") or ""

    @property
    def videos(self) -> Iterator[ChannelVideoItem]:
        meta = self._ensure_meta()
        fallback = {"channel": meta.get("channel"), "channel_id": meta.get("channel_id")}
        for e in (meta.get("entries") or []):
            if not e:
                continue
            yield ChannelVideoItem(e, fallback_channel=fallback)

    @property
    def video_urls(self) -> list[str]:
        return [v.watch_url for v in self.videos]

    @property
    def playlists(self) -> Iterator["PlaylistSummary"]:
        # Separate Abfrage auf /playlists
        url = _channel_subpage_url(self.channel_url, "playlists")
        try:
            info = _ydl_extract(url, extra_opts={"extract_flat": "in_playlist"})
        except Exception as e:
            logger.warning(f"ChannelAdapter.playlists: {e}")
            return
        for e in (info.get("entries") or []):
            if not e:
                continue
            yield PlaylistSummary(e)

    # initial_data-Shim — nur soweit Altcode drauf zugreift
    @property
    def initial_data(self) -> dict:
        return {"metadata": {"channelMetadataRenderer": {
            "title": self.channel_name,
            "description": self.description,
            "externalId": self.channel_id,
            "avatar": {"thumbnails": [{"url": self.thumbnail_url}]} if self.thumbnail_url else {},
        }}}


class PlaylistSummary:
    __slots__ = ("title", "playlist_id", "playlist_url")

    def __init__(self, entry: dict):
        self.title = entry.get("title") or ""
        self.playlist_id = entry.get("id") or ""
        self.playlist_url = entry.get("url") or (
            f"https://www.youtube.com/playlist?list={self.playlist_id}" if self.playlist_id else ""
        )


def _channel_videos_url(url: str) -> str:
    """Stellt sicher, dass wir /videos-Seite abfragen."""
    if url.rstrip("/").endswith("/videos"):
        return url
    if "/playlist" in url or "list=" in url:
        return url
    return url.rstrip("/") + "/videos"


def _channel_subpage_url(url: str, sub: str) -> str:
    base = url.rstrip("/")
    for suffix in ("/videos", "/shorts", "/streams", "/playlists", "/about"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{sub}"


# ═══════════════════════════════════════════════════════════════════
#  PLAYLIST
# ═══════════════════════════════════════════════════════════════════

class PlaylistAdapter:
    """pytubefix.Playlist-kompatibel."""

    def __init__(self, url: str, *, max_videos: Optional[int] = None, **_kwargs):
        self.playlist_url = url
        self._max_videos = max_videos
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            opts = {"extract_flat": "in_playlist"}
            if self._max_videos:
                opts["playlistend"] = self._max_videos
            self._info = _ydl_extract(self.playlist_url, extra_opts=opts)
        return self._info

    @property
    def playlist_id(self) -> str:
        info = self._ensure()
        pid = info.get("id") or ""
        # Falls wir auf /watch mit list= sind
        if not pid:
            try:
                q = parse_qs(urlparse(self.playlist_url).query)
                pid = (q.get("list") or [""])[0]
            except Exception:
                pass
        return pid

    @property
    def title(self) -> str:
        return self._ensure().get("title") or ""

    @property
    def description(self) -> str:
        return self._ensure().get("description") or ""

    @property
    def owner(self) -> str:
        return self._ensure().get("uploader") or self._ensure().get("channel") or ""

    @property
    def owner_id(self) -> str:
        return self._ensure().get("channel_id") or self._ensure().get("uploader_id") or ""

    @property
    def length(self) -> int:
        info = self._ensure()
        return int(info.get("playlist_count") or len(info.get("entries") or []))

    @property
    def videos(self) -> Iterator[ChannelVideoItem]:
        info = self._ensure()
        fallback = {"channel": info.get("uploader"), "channel_id": info.get("channel_id")}
        for e in (info.get("entries") or []):
            if not e:
                continue
            yield ChannelVideoItem(e, fallback_channel=fallback)

    @property
    def video_urls(self) -> list[str]:
        return [v.watch_url for v in self.videos]

    # _html_data-Shim (Altcode in search.py greift auf title-Fallback zu)
    @property
    def _html_data(self) -> dict:
        return {"title": {"runs": [{"text": self.title}]}}


# ═══════════════════════════════════════════════════════════════════
#  SEARCH
# ═══════════════════════════════════════════════════════════════════

class SearchAdapter:
    """pytubefix.Search-kompatibel.

    yt-dlp 'ytsearchN:query' liefert nur Videos (keine kategorisierte Aufteilung
    in Playlists/Channels wie bei YouTube-UI). Wir extrahieren:
      - videos: direkt aus entries
      - shorts: Videos mit duration ≤ 60s
      - playlists/channels: leere Liste (yt-dlp kann das über ytsearch nicht)

    Für pytubefix-Kompatibilität gibt es die Singular-Aliase playlist/channel/
    completion_suggestions zusätzlich — damit der bestehende Router-Code
    (s.playlist[:6], s.channel[:4]) nicht in AttributeError läuft.
    """

    def __init__(self, query: str, *, max_results: int = 25, **_kwargs):
        self.query = query
        self._max = max_results
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            self._info = _ydl_extract(
                f"ytsearch{self._max}:{self.query}",
                extra_opts={"extract_flat": True},
            )
        return self._info

    # ── Video-Kategorien (aus ytsearch) ─────────────────────────────
    # videos enthält ALLE Treffer (auch Shorts) — damit UIs, die nur
    # 'videos' lesen, keine Shorts verlieren. shorts ist die Untermenge
    # mit duration ≤ 60s, für UIs die beides getrennt anzeigen wollen.

    @property
    def videos(self) -> list[ChannelVideoItem]:
        entries = self._ensure().get("entries") or []
        return [ChannelVideoItem(e) for e in entries if e and e.get("id")]

    @property
    def shorts(self) -> list[ChannelVideoItem]:
        return [v for v in self.videos if 0 < v.length <= 60]

    # ── Playlists / Channels: nicht verfügbar über ytsearch ─────────

    @property
    def playlists(self) -> list[PlaylistSummary]:
        # yt-dlp ytsearch liefert keine Playlist-Entries — wäre separater
        # Call nötig (YouTube-Search-URL mit sp=Filter). Bleibt leer bis
        # echter Bedarf.
        return []

    @property
    def channels(self) -> list:
        return []

    @property
    def suggestions(self) -> list[str]:
        return []

    # ── pytubefix-Kompat: Singular-Aliase ───────────────────────────
    # Alter Router-Code (search.py) nutzt s.playlist / s.channel /
    # s.completion_suggestions (pytubefix-Namen). Wir mappen auf unsere
    # Plural-Properties, damit try/except nicht mehr alle Fehler schluckt.

    @property
    def playlist(self) -> list[PlaylistSummary]:
        return self.playlists

    @property
    def channel(self) -> list:
        return self.channels

    @property
    def completion_suggestions(self) -> list[str]:
        return self.suggestions
