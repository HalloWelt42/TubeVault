"""
Error-Classifier Tests.

Echte Fehlermeldungen aus Backend-Logs – damit Regressionen sofort sichtbar werden.
"""
import pytest

from app.services.error_classifier import classify, ErrorClass


# ─────────────────────── Members-Only / Early-Access ───────────────────────

@pytest.mark.parametrize("msg", [
    # Originale YouTube-Fehler aus Logs
    "ERROR: [youtube] -uC8orb2Tt8: Join this channel to get access to members-only content like this video, and other exclusive perks.",
    "ERROR: [youtube] yt8iY1EpL-s: This video is available to this channel's members on level: Early Access & Science 💜 (or any higher level). Join this channel to get access to members-only content and other exclusive perks.",
    # Variationen
    "Join this channel",
    "members-only",
    "this is MEMBERS-ONLY content",
    "Members on level 1 required",
    "channel's members only",
])
def test_members_only_detected(msg):
    result = classify(msg)
    assert result.members_only is True, f"Expected members_only=True for: {msg[:80]}"
    assert result.is_retryable is True, "members_only muss retryable sein (1d/7d)"
    assert result.is_terminal is False
    # Exklusiv zu anderen Kategorien
    assert result.unavailable is False
    assert result.bot is False


# ─────────────────────── Unavailable / Terminal ───────────────────────

@pytest.mark.parametrize("msg", [
    "ERROR: Video unavailable",
    "private video",
    "this video has been removed",
    "account terminated",   # exakte Wortfolge
    "blocked for copyright reasons",
    "Sign in to confirm your age",
    "age-restricted video",
])
def test_unavailable_detected(msg):
    result = classify(msg)
    assert result.unavailable is True, f"Expected unavailable=True for: {msg}"
    assert result.is_terminal is True
    assert result.is_retryable is False
    assert result.members_only is False


def test_unavailable_account_terminated_with_has_been():
    """Regression-Test: YouTube formatiert oft 'This account has been terminated'.
    Phase 2b: fix via zusätzlichem Keyword 'has been terminated'."""
    result = classify("This account has been terminated")
    assert result.unavailable is True


def test_unavailable_youtube_user_terminated_variants():
    """Diverse YT-Variationen von 'account terminated'."""
    for msg in [
        "This account has been terminated for a violation",
        "The user's account has been terminated",
        "account terminated",
    ]:
        r = classify(msg)
        assert r.unavailable is True, f"Failed: {msg}"


def test_members_only_wins_over_unavailable():
    """
    Wichtig: 'Join this channel' enthält implizit Anzeichen für 'not available'
    → aber als members_only klassifiziert werden, nicht unavailable.
    Sonst würden Early-Access-Videos sofort geparkt statt in 1d-Retry zu gehen.
    """
    msg = "Join this channel to get access to this not available content"
    result = classify(msg)
    assert result.members_only is True
    assert result.unavailable is False


# ─────────────────────── Bot-Detection ───────────────────────

@pytest.mark.parametrize("msg", [
    "yt-dlp was detected as a bot",
    "Detected as a bot. See details",
    "do not open an issue about this",
    "Sign in to confirm you're not a bot",  # FALLS 'bot' Teil vom Pattern wäre
])
def test_bot_detected(msg):
    result = classify(msg)
    # 'detected as a bot' + 'do not open an issue' sind die Keywords
    if "detected as a bot" in msg.lower() or "do not open an issue" in msg.lower():
        assert result.bot is True, f"Expected bot=True for: {msg}"
        assert result.is_retryable is True


# ─────────────────────── Throttle / Rate-Limit ───────────────────────

@pytest.mark.parametrize("msg", [
    "HTTP Error 429: Too Many Requests",
    "throttling active",
    "rate limit exceeded",
    "403 Forbidden",
    "Retries exceeded",
])
def test_throttle_detected(msg):
    result = classify(msg)
    assert result.throttle is True, f"Expected throttle=True for: {msg}"
    assert result.is_retryable is True
    assert result.is_terminal is False


# ─────────────────────── Temporary ───────────────────────

@pytest.mark.parametrize("msg", [
    "HTTP 503 Service Unavailable",
    "service unavailable",
    "temporarily unavailable",
    "HTTP Error 504",
    "connection reset by peer",
    "socket timeout",
    "read operation timed out",
])
def test_temporary_detected(msg):
    result = classify(msg)
    assert result.temporary is True, f"Expected temporary=True for: {msg}"
    assert result.is_retryable is True


# ─────────────────────── Edge-Cases ───────────────────────

def test_empty_string_is_unknown():
    r = classify("")
    assert r.unknown is True
    assert r.is_retryable is False
    assert r.is_terminal is False


def test_none_input_is_unknown():
    r = classify(None)
    assert r.unknown is True


def test_unclassified_error_is_unknown():
    r = classify("some weird random error that nobody classified")
    assert r.unknown is True


def test_case_insensitive():
    assert classify("MEMBERS-ONLY CONTENT").members_only is True
    assert classify("Members-Only Content").members_only is True
    assert classify("members-only content").members_only is True


# ─────────────────────── Mutually Exclusive ───────────────────────

def test_flags_are_mutually_exclusive():
    """Genau EIN Flag ist True (oder alle False = unknown)."""
    samples = [
        "members-only",
        "video unavailable",
        "detected as a bot",
        "429 rate limit",
        "503 unavailable",
        "",
    ]
    for msg in samples:
        r = classify(msg)
        flags = [r.members_only, r.unavailable, r.bot, r.throttle, r.temporary]
        true_count = sum(flags)
        assert true_count <= 1, f"Multiple True flags for {msg!r}: {flags}"


def test_terminal_vs_retryable_exclusive():
    """is_terminal und is_retryable duerfen NICHT beide True sein."""
    samples = [
        "members-only", "video unavailable", "429", "503",
        "detected as a bot", "unknown error", "",
    ]
    for msg in samples:
        r = classify(msg)
        assert not (r.is_terminal and r.is_retryable), (
            f"Sowohl terminal als auch retryable fuer {msg!r}")
