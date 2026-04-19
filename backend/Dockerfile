FROM python:3.12-slim

LABEL maintainer="HalloWelt42"
LABEL version="1.0.0"
LABEL description="TubeVault Backend – Video-Vault & Streaming API"

# System-Abhängigkeiten
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Deno für yt-dlp JavaScript-Runtime (löst n-challenge + signature).
# Architektur-agnostisch (arm64 auf Pi, x86_64 auf x86).
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
        aarch64|arm64) DENO_ARCH="aarch64-unknown-linux-gnu" ;; \
        x86_64) DENO_ARCH="x86_64-unknown-linux-gnu" ;; \
        *) echo "Unbekannte Architektur: $ARCH"; exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/denoland/deno/releases/latest/download/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip && \
    unzip /tmp/deno.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/deno && \
    rm /tmp/deno.zip && \
    deno --version

# Arbeitsverzeichnis
WORKDIR /app

# Python Dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt \
    && pip install --no-cache-dir --timeout=120 --retries=5 -r requirements-dev.txt

# App-Code
COPY app/ ./app/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Daten-Verzeichnisse
RUN mkdir -p /app/data/{videos,audio,thumbnails,metadata,subtitles,db,exports,temp,scan} \
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
