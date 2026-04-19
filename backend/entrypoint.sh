#!/bin/bash
# TubeVault Backend Entrypoint v1.5.58
# Startet NUR Uvicorn – RSS-Polling wird extern per System-Cron angestoßen
# © HalloWelt42 – Private Nutzung

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  TubeVault Backend v1.5.58               ║"
echo "║  RSS: extern per Cron → /tick            ║"
echo "╚══════════════════════════════════════════╝"

exec uvicorn app.main:app --host 0.0.0.0 --port 8031 --workers 1
