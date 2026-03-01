#!/bin/bash
# TubeVault Backend Entrypoint v1.5.59
# Startet NUR Uvicorn -  RSS-Polling wird extern per System-Cron angestoßen
# © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
# SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  TubeVault Backend v1.5.59               ║"
echo "║  RSS: extern per Cron → /tick            ║"
echo "╚══════════════════════════════════════════╝"

# Datenverzeichnisse sicherstellen (falls Volumes noch leer)
DATA_DIR="${TUBEVAULT_DATA_DIR:-/app/data}"
for dir in videos audio thumbnails metadata subtitles avatars banners db exports temp scan rss_thumbs texts backups; do
    mkdir -p "$DATA_DIR/$dir"
done
mkdir -p "${TUBEVAULT_CONFIG_DIR:-/app/config}"

echo "→ Datenverzeichnisse geprüft: $DATA_DIR"

exec uvicorn app.main:app --host 0.0.0.0 --port 8031 --workers 1
