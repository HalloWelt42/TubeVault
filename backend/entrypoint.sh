#!/bin/bash
# TubeVault Backend Entrypoint v1.5.58
# Startet NUR Uvicorn – RSS-Polling wird extern per System-Cron angestoßen
# © HalloWelt42 – Private Nutzung

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  TubeVault Backend v1.5.58               ║"
echo "║  RSS: extern per Cron → /tick            ║"
echo "╚══════════════════════════════════════════╝"

# Nur IPv4: "::" nähme unter asyncio ausschließlich IPv6 an (Cron und Port 8031 wären zu). Dass der Name
# tubevault-backend auch auf eine IPv6-Adresse auflöst, fängt nginx ab (max_fails=0, nächste Adresse; HELF-158).
exec uvicorn app.main:app --host 0.0.0.0 --port 8031 --workers 1
