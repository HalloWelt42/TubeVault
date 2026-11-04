#!/bin/bash
# TubeVault Backend Entrypoint v1.5.58
# Startet NUR Uvicorn – RSS-Polling wird extern per System-Cron angestoßen
# © HalloWelt42 – Private Nutzung

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  TubeVault Backend v1.5.58               ║"
echo "║  RSS: extern per Cron → /tick            ║"
echo "╚══════════════════════════════════════════╝"

# "::" nimmt IPv4 und IPv6 an: das Compose-Netz hat IPv6, und der Name tubevault-backend löst auch auf die
# IPv6-Adresse auf. Mit 0.0.0.0 lief jeder Aufruf über IPv6 ins Leere (HELF-158).
exec uvicorn app.main:app --host :: --port 8031 --workers 1
