FROM python:3.12-slim

LABEL maintainer="HalloWelt42"
LABEL version="1.1.0"
LABEL description="TubeVault Backend – Video-Vault & Streaming API"

# System-Abhängigkeiten
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis
WORKDIR /app

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt

# App-Code
COPY app/ ./app/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Daten-Verzeichnisse (keine Brace Expansion – sh/dash kompatibel)
RUN mkdir -p /app/data/videos \
             /app/data/audio \
             /app/data/thumbnails \
             /app/data/metadata \
             /app/data/subtitles \
             /app/data/avatars \
             /app/data/banners \
             /app/data/db \
             /app/data/exports \
             /app/data/temp \
             /app/data/scan \
             /app/data/rss_thumbs \
             /app/data/texts \
             /app/data/backups \
             /app/config

# Port
EXPOSE 8031

# Umgebungsvariablen für Cron-Konfiguration
ENV RSS_POLL_INTERVAL=300
ENV RSS_MAX_FEEDS=30

# Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8031/api/system/health || exit 1

# Start via Entrypoint (Uvicorn + Cron-Loop)
CMD ["./entrypoint.sh"]
