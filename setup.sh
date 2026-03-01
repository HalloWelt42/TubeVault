#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  TubeVault -  Setup Script v1.1.0                            ║
# ║  Erstellt Verzeichnisse und .env für Erstinstallation.      ║
# ║  Unterstützt: Linux (Raspberry Pi, Debian, Ubuntu), macOS   ║
# ║  Windows: setup.ps1 verwenden                               ║
# ║  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
# SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0                           ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

PLATFORM="$(uname -s)"

# ── Windows-Erkennung (Git Bash / MSYS / MINGW) ─────────────
case "$PLATFORM" in
    MINGW*|MSYS*|CYGWIN*)
        echo ""
        echo "⚠️  Windows erkannt ($PLATFORM)"
        echo ""
        echo "   Dieses Skript ist für Linux/macOS."
        echo "   Verwende stattdessen das PowerShell-Skript:"
        echo ""
        echo "   powershell -ExecutionPolicy Bypass -File setup.ps1"
        echo ""
        echo "   Oder in PowerShell direkt:"
        echo "   .\\setup.ps1"
        echo ""
        exit 1
        ;;
esac

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  TubeVault -  Setup                      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Docker prüfen ──────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "❌ Docker ist nicht installiert."
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "   Installiere Docker Desktop für Mac:"
        echo "   https://www.docker.com/products/docker-desktop/"
    else
        echo "   Installiere Docker mit: curl -fsSL https://get.docker.com | sh"
        echo "   Danach: sudo usermod -aG docker \$USER && newgrp docker"
    fi
    exit 1
fi

# Docker Daemon prüfen (Docker Desktop muss laufen)
if ! docker info &> /dev/null; then
    echo "❌ Docker Daemon läuft nicht."
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "   Starte Docker Desktop und warte bis das Icon grün wird."
    else
        echo "   Starte Docker mit: sudo systemctl start docker"
    fi
    exit 1
fi

# Docker Compose prüfen
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose ist nicht verfügbar."
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "   Docker Compose ist in Docker Desktop enthalten."
        echo "   Bitte Docker Desktop aktualisieren."
    else
        echo "   Installiere Docker Compose Plugin: sudo apt install docker-compose-plugin"
    fi
    exit 1
fi

# Versionen anzeigen (grep ohne -P für macOS-Kompatibilität)
DOCKER_VER=$(docker --version | grep -o '[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*' | head -1)
echo "✅ Docker $DOCKER_VER"
echo "✅ Docker Compose $(docker compose version --short)"
echo ""

# ── Verzeichnisse anlegen ──────────────────────────────────────
echo "📁 Erstelle Datenverzeichnisse..."
DIRS=(
    "data/db"
    "data/videos"
    "data/audio"
    "data/thumbnails"
    "data/avatars"
    "data/metadata"
    "data/banners"
    "data/subtitles"
    "data/exports"
    "data/temp"
    "data/rss_thumbs"
    "data/texts"
    "data/scan"
    "data/backups"
    "config"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$dir"
    echo "   ✓ $dir"
done
echo ""

# ── .env erstellen ─────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "📝 .env erstellt (aus .env.example)"
    echo "   → Passe die Werte in .env nach Bedarf an."
else
    echo "📝 .env existiert bereits -  wird nicht überschrieben."
fi
echo ""

# ── System-Info (plattformunabhängig) ──────────────────────────
get_os_name() {
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "macOS $(sw_vers -productVersion 2>/dev/null || echo '')"
    elif [ -f /etc/os-release ]; then
        grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"'
    else
        echo "Linux (unbekannt)"
    fi
}

get_ram() {
    if [ "$PLATFORM" = "Darwin" ]; then
        # macOS: sysctl gibt Bytes zurück
        local bytes
        bytes=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
        echo "$((bytes / 1073741824)) GB"
    else
        free -h 2>/dev/null | awk '/^Mem:/{print $2}' || echo "unbekannt"
    fi
}

get_disk_free() {
    df -h . 2>/dev/null | awk 'NR==2{print $4}' || echo "unbekannt"
}

get_local_ip() {
    if [ "$PLATFORM" = "Darwin" ]; then
        ipconfig getifaddr en0 2>/dev/null || echo "localhost"
    else
        hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost"
    fi
}

echo "📊 System-Info:"
echo "   Plattform:  $PLATFORM ($(uname -m))"
echo "   OS:         $(get_os_name)"
echo "   RAM:        $(get_ram)"
echo "   Disk frei:  $(get_disk_free)"
echo ""

# ── Speicherplatz-Warnung ──────────────────────────────────────
DISK_FREE_KB=$(df . 2>/dev/null | awk 'NR==2{print $4}' || echo "0")
# macOS df zeigt Blöcke à 512 Byte, Linux à 1024 Byte
if [ "$PLATFORM" = "Darwin" ]; then
    DISK_FREE_KB=$((DISK_FREE_KB / 2))
fi

if [ "$DISK_FREE_KB" -lt 10485760 ] 2>/dev/null; then
    echo "⚠️  Weniger als 10 GB frei!"
    echo "   TubeVault speichert Videos lokal -  für größere Sammlungen"
    echo "   wird mehr Speicherplatz empfohlen."
    echo ""
fi

# ── Fertig ─────────────────────────────────────────────────────
LOCAL_IP=$(get_local_ip)

echo "🚀 Setup abgeschlossen! Starte TubeVault mit:"
echo ""
echo "   docker compose up -d --build"
echo ""
echo "   Frontend: http://${LOCAL_IP}:8032"
echo "   Backend:  http://${LOCAL_IP}:8031/docs"
echo ""
