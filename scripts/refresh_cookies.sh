#!/usr/bin/env bash
#
# TubeVault – Cookies aus dem Pi-Browser ins Backend-Config-Volume ziehen.
#
# Zwei Profile-Strategie:
#   - cookies.txt        → ANON (immer aktiv, hilft gegen leichte Bot-Detection)
#   - cookies-login.txt  → LOGIN (optional, nur als Eskalation für Härtefälle)
#
# Setup für Login-Profile:
#   mkdir -p ~/.config/chromium-yt-login
#   chromium --user-data-dir=$HOME/.config/chromium-yt-login   # einmal manuell
#     auf youtube.com einloggen, danach läuft der Cron automatisch.
#
# Cron-Eintrag (alle 6h):
#   0 */6 * * * /home/pi/tubevault/scripts/refresh_cookies.sh \
#       >> /home/pi/tubevault/logs/cookies-refresh.log 2>&1
#
set -euo pipefail

CONFIG_DIR="/home/pi/tubevault/config"
LOG_DIR="/home/pi/tubevault/logs"
COOKIES_ANON="$CONFIG_DIR/cookies.txt"
COOKIES_LOGIN="$CONFIG_DIR/cookies-login.txt"
YTDLP="/home/pi/.local/yt-dlp-venv/bin/yt-dlp"

# Login-Profile: Default-Pfad. Anderer Pfad per ENV überschreibbar.
LOGIN_PROFILE_DIR="${LOGIN_PROFILE_DIR:-/home/pi/.config/chromium-yt-login}"

mkdir -p "$CONFIG_DIR" "$LOG_DIR"

if [ ! -x "$YTDLP" ]; then
    echo "[refresh_cookies] yt-dlp venv fehlt: $YTDLP"
    echo "  Setup: python3 -m venv /home/pi/.local/yt-dlp-venv && $_/bin/pip install yt-dlp"
    exit 1
fi

ts=$(date '+%F %T')

# ─── 1. ANON: aus dem Default-Chromium-Profile (Standard für alle Calls) ───────
echo "[$ts] anon: ziehe aus chromium (Default-Profile)"
if "$YTDLP" \
        --cookies-from-browser chromium \
        --cookies "$COOKIES_ANON" \
        --skip-download --quiet --no-warnings \
        https://www.youtube.com/ 2>/dev/null
then
    n=$(awk -F'\t' '/^[^#]/ && $1 ~ /youtube\.com$/ {n++} END{print n+0}' "$COOKIES_ANON")
    sz=$(wc -c < "$COOKIES_ANON")
    echo "[$ts] anon: OK – $n YouTube-Cookies, ${sz} Bytes"
else
    echo "[$ts] anon: Extraktion fehlgeschlagen (Browser zu? Profile leer?)"
fi

# ─── 2. LOGIN (optional): nur wenn Login-Profile existiert ────────────────────
if [ -d "$LOGIN_PROFILE_DIR" ] && [ -f "$LOGIN_PROFILE_DIR/Default/Cookies" ]; then
    echo "[$ts] login: Profile gefunden – $LOGIN_PROFILE_DIR"
    if "$YTDLP" \
            --cookies-from-browser "chromium:$LOGIN_PROFILE_DIR" \
            --cookies "$COOKIES_LOGIN" \
            --skip-download --quiet --no-warnings \
            https://www.youtube.com/ 2>/dev/null
    then
        n=$(awk -F'\t' '/^[^#]/ && $1 ~ /youtube\.com$/ {n++} END{print n+0}' "$COOKIES_LOGIN")
        sz=$(wc -c < "$COOKIES_LOGIN")
        # Login-Token (SAPISID/SID) als Indikator dass wir wirklich eingeloggt sind
        has_login=$(grep -cE '\b(SAPISID|__Secure-3PSID|HSID)\b' "$COOKIES_LOGIN" 2>/dev/null || echo 0)
        if [ "$has_login" -gt 0 ]; then
            echo "[$ts] login: OK – $n Cookies, ${sz} Bytes, eingeloggt (Login-Token gefunden)"
        else
            echo "[$ts] login: WARNUNG – Profile existiert aber keine Login-Tokens. Nicht eingeloggt?"
        fi
    else
        echo "[$ts] login: Extraktion fehlgeschlagen"
    fi
else
    echo "[$ts] login: Profile $LOGIN_PROFILE_DIR existiert nicht – übersprungen"
fi
