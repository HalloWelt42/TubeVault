# TubeVault v1.0.0

**Selbstgehostetes Video-Vault & Streaming-System**

© HalloWelt42 – Private Nutzung

## Stack

- **Backend:** Python FastAPI + pytubefix + FFmpeg + SQLite
- **Frontend:** Svelte 5 (kommt in Phase 2)
- **Deployment:** Docker Compose auf Raspberry Pi 5
- **Ports:** Backend 8031, Frontend 8032

## Schnellstart

### 1. System-Analyse (auf dem Pi)

```bash
bash scripts/analyze-system.sh
```

### 2. Backend starten

```bash
# Nur Backend (Frontend kommt später)
docker compose up -d tubevault-backend
```

### 3. Prüfen

```bash
# Health Check
curl http://192.168.178.49:8031/api/system/health

# API Docs
# Browser: http://192.168.178.49:8031/docs
```

## API Endpunkte

| Bereich | Endpunkt | Beschreibung |
|---------|----------|-------------|
| Videos | `GET /api/videos` | Alle Videos abrufen |
| Videos | `GET /api/videos/info?url=...` | YouTube-Info abrufen |
| Downloads | `POST /api/downloads` | Video herunterladen |
| Downloads | `GET /api/downloads` | Queue-Status |
| Player | `GET /api/player/{id}` | Video streamen |
| Favoriten | `GET /api/favorites` | Favoriten abrufen |
| Kategorien | `GET /api/categories` | Kategorien-Baum |
| Settings | `GET /api/settings` | Einstellungen |
| System | `GET /api/system/stats` | System-Statistiken |

Vollständige API-Docs: `http://192.168.178.49:8031/docs`

## Projektstruktur

```
tubevault/
├── backend/              # FastAPI Backend
│   ├── app/
│   │   ├── main.py       # App-Entry
│   │   ├── config.py     # Konfiguration
│   │   ├── database.py   # SQLite Schema
│   │   ├── routers/      # API-Endpunkte
│   │   ├── services/     # Business-Logic
│   │   ├── models/       # Pydantic Models
│   │   └── utils/        # Hilfsfunktionen
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/             # Svelte 5 (Phase 2)
│   ├── Dockerfile
│   └── nginx.conf
├── data/                 # Persistente Daten
│   ├── videos/
│   ├── audio/
│   ├── thumbnails/
│   ├── db/
│   └── temp/
├── config/
├── scripts/
│   └── analyze-system.sh
├── docker-compose.yml
└── LICENSE
```

## Daten-Verzeichnis

Alle Video-Daten liegen auf `/mnt/data/tubevault/data/` (separate 1.8TB Partition).
Config bleibt im Projektordner unter `./config/`.
Bei 1.7 TB frei: ca. 5.900 Videos (1080p, 10min) möglich.
