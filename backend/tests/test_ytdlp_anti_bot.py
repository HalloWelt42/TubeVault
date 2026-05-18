"""
Anti-Bot Tests für ytdlp_adapter.

Sichert die Random-Pool-Strategie ab:
- Player-Client-Pool ist nicht leer und liefert Listen mit ≥1 Element
- User-Agent-Pool ist nicht leer und liefert valide UA-Strings
- _ua_short klassifiziert die wichtigsten Browser-Familien
- _classify_yt_error erkennt Bot-/Members-/Age-/HTTP-Fehler
- _build_ydl_opts setzt POT-Provider, EJS, optional Cookies, Random-Client/UA
- Wiederholte Calls liefern unterschiedliche Strategien (statistisch)
"""
import pytest

from app.utils.ytdlp_adapter import (
    _PLAYER_CLIENT_POOL,
    _USER_AGENT_POOL,
    _PERMANENT_CATEGORIES,
    _MAX_RETRIES,
    _pick_player_clients,
    _pick_user_agent,
    _ua_short,
    _classify_yt_error,
    _build_ydl_opts,
    _strategy_for_call,
    _should_retry,
)


def test_player_client_pool_non_empty():
    assert len(_PLAYER_CLIENT_POOL) >= 4
    for entry in _PLAYER_CLIENT_POOL:
        assert isinstance(entry, list) and len(entry) >= 1
        for c in entry:
            assert isinstance(c, str) and c


def test_user_agent_pool_realistic():
    assert len(_USER_AGENT_POOL) >= 5
    for ua in _USER_AGENT_POOL:
        assert ua.startswith("Mozilla/5.0")
        # Mindestens eine bekannte Engine drin
        assert any(k in ua for k in ("Chrome/", "Firefox/", "Safari/", "Gecko"))


def test_pick_returns_pool_member():
    for _ in range(20):
        clients = _pick_player_clients()
        assert clients in _PLAYER_CLIENT_POOL or any(
            clients == p for p in _PLAYER_CLIENT_POOL
        )
        assert _pick_user_agent() in _USER_AGENT_POOL


def test_picks_actually_vary():
    """Statistik: aus 30 Calls sollten min. 3 verschiedene Strategien kommen."""
    seen_clients = set()
    seen_ua = set()
    for _ in range(30):
        seen_clients.add(tuple(_pick_player_clients()))
        seen_ua.add(_pick_user_agent())
    assert len(seen_clients) >= 3, "Pool zu klein oder Random kaputt"
    assert len(seen_ua) >= 3


def test_ua_short_classification():
    assert _ua_short("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) ...") == "iPhone"
    assert _ua_short("Mozilla/5.0 (Linux; Android 14; Pixel 8) ...") == "Android"
    assert _ua_short("Mozilla/5.0 (Macintosh; ...) Version/18.0 Safari/605.1.15") == "Safari-Mac"
    assert _ua_short("Mozilla/5.0 (Windows NT 10.0; ...) Chrome/132.0.0.0 Safari/537.36") == "Chrome-Win"
    assert _ua_short("Mozilla/5.0 (X11; Linux x86_64) Chrome/132 ...") == "Chrome-Linux"
    assert _ua_short("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Firefox/131.0") == "Firefox-Linux"
    assert _ua_short("etwas ganz anderes") == "Other"


def test_classify_error_categories():
    assert _classify_yt_error("Sign in to confirm you're not a bot") == "BOT-DETECTION"
    assert _classify_yt_error("Sign in to confirm your age") == "AGE-GATE"
    assert _classify_yt_error("Join this channel to get access to members-only") == "MEMBERS-ONLY"
    assert _classify_yt_error("This video is available to this channel's members on level: x") == "MEMBERS-ONLY"
    assert _classify_yt_error("Private video") == "PRIVATE"
    # GEO-BLOCKED bekommt eigene Kategorie (vor UNAVAILABLE matchen)
    assert _classify_yt_error("The uploader has not made this video available in your country") == "GEO-BLOCKED"
    assert _classify_yt_error("Video not available in your country") == "GEO-BLOCKED"
    # LIVE-COMING ist kein Fehler, sondern "Stream startet später"
    assert _classify_yt_error("This live event will begin in a few moments.") == "LIVE-COMING"
    assert _classify_yt_error("Premieres in 30 minutes") == "LIVE-COMING"
    assert _classify_yt_error("Video unavailable") == "UNAVAILABLE"
    assert _classify_yt_error("This video has been removed") == "REMOVED"
    assert _classify_yt_error("HTTP Error 429: Too Many Requests") == "RATE-429"
    assert _classify_yt_error("HTTP Error 403: Forbidden") == "HTTP-4xx"
    assert _classify_yt_error("HTTP Error 503") == "HTTP-5xx"
    assert _classify_yt_error("operation timed out") == "TIMEOUT"
    assert _classify_yt_error("") == "unknown"


def test_geo_blocked_is_permanent():
    """GEO-BLOCKED kann nicht durch Player-Client-Wechsel gelöst werden."""
    assert _should_retry("GEO-BLOCKED") is False


def test_build_ydl_opts_has_required_anti_bot_keys():
    opts = _build_ydl_opts(label="testvid")
    # POT-Provider konfiguriert
    pot = opts["extractor_args"]["youtubepot-bgutilhttp"]["base_url"]
    assert pot and pot[0].startswith("http")
    # Player-Clients aus Pool
    clients = opts["extractor_args"]["youtube"]["player_client"]
    assert clients in _PLAYER_CLIENT_POOL
    # EJS für Signature/N-Challenge
    assert "ejs:github" in opts["remote_components"]
    # Random User-Agent gesetzt
    ua = opts["http_headers"]["User-Agent"]
    assert ua in _USER_AGENT_POOL
    # Standard-Mode = Metadaten-Extract → kein Download
    assert opts["skip_download"] is True


def test_build_ydl_opts_for_download():
    opts = _build_ydl_opts(label="testvid", for_download=True)
    # Bei echten Downloads kein skip_download
    assert "skip_download" not in opts or opts["skip_download"] is False


def test_strategy_for_call_returns_clients_and_ua():
    clients, ua = _strategy_for_call(label="abc123")
    assert clients in _PLAYER_CLIENT_POOL
    assert ua in _USER_AGENT_POOL


def test_build_ydl_opts_uses_cookies_when_file_exists(tmp_path, monkeypatch):
    """Wenn /app/config/cookies.txt da ist, wird sie gesetzt – sonst nicht."""
    from app.utils import ytdlp_adapter as mod

    # Schritt 1: Datei nicht da → kein cookiefile
    fake_path = str(tmp_path / "cookies.txt")
    monkeypatch.setattr(mod, "_cookiefile", lambda: None)
    opts = _build_ydl_opts(label="x")
    assert "cookiefile" not in opts

    # Schritt 2: Datei da → cookiefile gesetzt
    monkeypatch.setattr(mod, "_cookiefile", lambda: fake_path)
    opts = _build_ydl_opts(label="x")
    assert opts["cookiefile"] == fake_path


# ─── Auto-Retry-Logik ──────────────────────────────────────────────

def test_should_retry_permanent_categories():
    """Permanente Fehler dürfen NICHT retryt werden – wäre Verschwendung.
    PRIVATE/REMOVED/COPYRIGHT sind hier – Login löst die NICHT."""
    for cat in _PERMANENT_CATEGORIES:
        assert _should_retry(cat) is False, f"{cat} muss permanent sein"


def test_should_retry_recoverable_categories():
    """Bot/Rate/HTTP/Timeout/Format/Other → Retry mit anderer Strategie."""
    for cat in (
        "BOT-DETECTION", "RATE-429", "HTTP-4xx", "HTTP-5xx",
        "TIMEOUT", "UNAVAILABLE", "OTHER", "unknown",
    ):
        assert _should_retry(cat) is True, f"{cat} sollte retryt werden"


def test_members_only_is_login_dependent(tmp_path, monkeypatch):
    """MEMBERS-ONLY: ohne Login-Cookies = permanent, mit Login = retryable."""
    from app.utils import ytdlp_adapter as mod
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: None)
    assert _should_retry("MEMBERS-ONLY") is False  # ohne Login: gib auf
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: "/tmp/login.txt")
    assert _should_retry("MEMBERS-ONLY") is True   # mit Login: durch versuchen
    assert mod._needs_login_escalation("MEMBERS-ONLY") is True


def test_pick_excludes_already_tried():
    """Beim Retry darf nicht der gleiche Client nochmal kommen, solange noch
    andere im Pool sind."""
    first = _pick_player_clients()
    # 5 Tries: jedes Mal soll exclude greifen, bis Pool leer
    excluded = [first]
    for _ in range(min(5, len(_PLAYER_CLIENT_POOL) - 1)):
        nxt = _pick_player_clients(exclude=excluded)
        assert nxt not in excluded, f"exclude ignoriert! tried={excluded} got={nxt}"
        excluded.append(nxt)


def test_pick_falls_back_when_pool_exhausted():
    """Wenn alle Pool-Einträge ausgeschlossen sind, liefert die Funktion
    trotzdem etwas (Fallback auf normale Random-Wahl)."""
    all_excluded = list(_PLAYER_CLIENT_POOL)
    result = _pick_player_clients(exclude=all_excluded)
    assert result in _PLAYER_CLIENT_POOL  # irgendeiner zurück, kein None


def test_max_retries_sane():
    """Genug Versuche für 8er Pool, aber nicht endlos."""
    assert 1 <= _MAX_RETRIES <= 5


# ─── Login-Cookie-Eskalation ──────────────────────────────────────

def test_age_gate_only_retried_with_login(tmp_path, monkeypatch):
    """AGE-GATE ohne Login-Cookies → kein Retry (permanent)."""
    from app.utils import ytdlp_adapter as mod

    monkeypatch.setattr(mod, "_login_cookiefile", lambda: None)
    assert _should_retry("AGE-GATE") is False

    # Mit Login-Cookies → retry sinnvoll
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: "/tmp/fake-login.txt")
    assert _should_retry("AGE-GATE") is True


def test_needs_login_escalation_only_for_specific_cats(tmp_path, monkeypatch):
    """BOT-DETECTION/AGE-GATE/MEMBERS-ONLY eskalieren auf Login-Cookies
    (und nur wenn die Datei existiert) – Rate-Limits/Unavailable nicht."""
    from app.utils import ytdlp_adapter as mod
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: "/tmp/fake.txt")
    assert mod._needs_login_escalation("BOT-DETECTION") is True
    assert mod._needs_login_escalation("AGE-GATE") is True
    assert mod._needs_login_escalation("MEMBERS-ONLY") is True
    assert mod._needs_login_escalation("RATE-429") is False
    assert mod._needs_login_escalation("UNAVAILABLE") is False

    # Ohne Login-Datei → keine Eskalation
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: None)
    assert mod._needs_login_escalation("BOT-DETECTION") is False
    assert mod._needs_login_escalation("AGE-GATE") is False
    assert mod._needs_login_escalation("MEMBERS-ONLY") is False


def test_build_opts_default_uses_anon_cookies(tmp_path, monkeypatch):
    """Standard-Call → cookies.txt (anon), nicht cookies-login.txt."""
    from app.utils import ytdlp_adapter as mod
    monkeypatch.setattr(mod, "_cookiefile", lambda: "/anon.txt")
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: "/login.txt")
    opts = _build_ydl_opts(label="x", use_login_cookies=False)
    assert opts["cookiefile"] == "/anon.txt"


def test_build_opts_escalation_uses_login(tmp_path, monkeypatch):
    """Eskalations-Call → cookies-login.txt."""
    from app.utils import ytdlp_adapter as mod
    monkeypatch.setattr(mod, "_cookiefile", lambda: "/anon.txt")
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: "/login.txt")
    opts = _build_ydl_opts(label="x", use_login_cookies=True)
    assert opts["cookiefile"] == "/login.txt"


def test_build_opts_login_falls_back_to_anon_if_missing(tmp_path, monkeypatch):
    """Wenn Login-Eskalation gewünscht aber Datei fehlt → mind. anon nutzen,
    nicht ganz ohne Cookies dastehen."""
    from app.utils import ytdlp_adapter as mod
    monkeypatch.setattr(mod, "_cookiefile", lambda: "/anon.txt")
    monkeypatch.setattr(mod, "_login_cookiefile", lambda: None)
    opts = _build_ydl_opts(label="x", use_login_cookies=True)
    assert opts["cookiefile"] == "/anon.txt"


# ─── Format-Mismatch / spezifischere Klassifikation ──────────────────

def test_classify_format_mismatch():
    """'Requested format is not available' bekommt eigene Kategorie für
    Auto-Recovery durch Format-Selector-Öffnung."""
    assert _classify_yt_error(
        "ERROR: [youtube] xyz: Requested format is not available. Use --list-formats…"
    ) == "FORMAT-MISMATCH"


def test_format_mismatch_is_retryable():
    """FORMAT-MISMATCH ist nicht permanent – wird mit anderer Strategie retryt."""
    assert _should_retry("FORMAT-MISMATCH") is True


# ─── Permanent-Fail-Cache ────────────────────────────────────────────

def test_cache_marks_and_retrieves():
    from app.utils.ytdlp_adapter import _cache_clear, _cache_check, _cache_mark
    _cache_clear()
    assert _cache_check("abc12345xyz") is None  # 11 chars
    _cache_mark("abc12345xyz", "Members-only test")
    assert _cache_check("abc12345xyz") == "Members-only test"


def test_cache_ignores_invalid_video_ids():
    from app.utils.ytdlp_adapter import _cache_clear, _cache_check, _cache_mark
    _cache_clear()
    _cache_mark("", "x")
    assert _cache_check("") is None
    _cache_mark("toolong-foo-bar", "x")
    assert _cache_check("toolong-foo-bar") is None


def test_cache_ttl_expires(monkeypatch):
    from app.utils import ytdlp_adapter as mod
    mod._cache_clear()
    # Mark mit Timestamp 0 (uralt)
    mod._PERMANENT_FAIL_CACHE["aaaa1111bbb"] = (0.0, "altes Members-only")
    assert mod._cache_check("aaaa1111bbb") is None  # > 60s alt → weg
    # Auch aus Cache entfernt
    assert "aaaa1111bbb" not in mod._PERMANENT_FAIL_CACHE


# ─── Pytubefix-Fallback ──────────────────────────────────────────────

def test_pytubefix_fallback_returns_dict_or_none():
    """Fallback-Funktion liefert entweder ein Info-Dict oder None.
    Bei pytubefix-Fehler kein Crash."""
    from app.utils.ytdlp_adapter import _pytubefix_extract_fallback
    # Mit kaputter URL → None (nicht raisen)
    result = _pytubefix_extract_fallback(
        "https://www.youtube.com/watch?v=NOPE_invalid", "NOPE_invalid"
    )
    assert result is None or isinstance(result, dict)
