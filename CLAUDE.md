# CLAUDE.md - TubeVault AI Assistant Guide

## Project Overview

TubeVault is a self-hosted video vault for downloading, archiving, streaming, and managing YouTube videos. It runs on Raspberry Pi, Linux servers, and macOS via Docker Compose. The UI language is **German (de-DE)**.

- **Version:** 1.9.13
- **License:** Non-commercial use only (see LICENSE)
- **Author:** HalloWelt42

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLite (aiosqlite), pytubefix, FFmpeg |
| Frontend | Svelte 5, Vite 5, Vanilla CSS, FontAwesome 7 |
| Reverse Proxy | Nginx (inside frontend container) |
| Deployment | Docker Compose (two containers on a bridge network) |
| Target platforms | Raspberry Pi 4/5 (ARM64), Linux servers, macOS |

## Repository Structure

```
TubeVault/
├── backend/                    # FastAPI backend (Python)
│   ├── app/
│   │   ├── main.py             # App entry, lifespan, middleware, router registration
│   │   ├── config.py           # Paths, ports, version constants
│   │   ├── database.py         # SQLite schema (v28), migrations, DB class
│   │   ├── database_scan.py    # Separate scan index DB
│   │   ├── routers/            # 26 API router modules (FastAPI APIRouter)
│   │   ├── services/           # 16 business logic service modules
│   │   ├── models/             # Pydantic request/response models
│   │   └── utils/              # Helpers (file_utils, tag_utils, thumbnail_utils)
│   ├── Dockerfile              # Python 3.12-slim + FFmpeg
│   ├── entrypoint.sh           # Starts uvicorn on port 8031
│   └── requirements.txt        # Python dependencies
├── frontend/                   # Svelte 5 SPA
│   ├── src/
│   │   ├── main.js             # App entry point
│   │   ├── App.svelte          # Root component (routing, layout)
│   │   ├── lib/
│   │   │   ├── api/client.js   # REST API client (150+ methods)
│   │   │   ├── components/     # UI components (common/, layout/, settings/, video/, watch/)
│   │   │   ├── router/         # Custom SPA router (history.pushState-based)
│   │   │   ├── stores/         # Svelte stores (settings, theme, notifications, etc.)
│   │   │   ├── styles/         # Global CSS (buttons, grids, badges)
│   │   │   └── utils/          # Format and description parsing utilities
│   │   ├── routes/             # 15+ page components (Dashboard, Library, Watch, etc.)
│   │   └── tests/              # Vitest unit tests
│   ├── Dockerfile              # Multi-stage: Node 20 build -> Nginx Alpine
│   ├── nginx.conf              # SPA routing + API reverse proxy
│   ├── vite.config.js          # Dev server on port 5173, API proxy to :8031
│   ├── vitest.config.js        # jsdom environment, tests in src/**/*.test.js
│   └── package.json
├── docker-compose.yml          # Two services: tubevault-backend, tubevault-frontend
├── .env.example                # Environment variable template
├── setup.sh                    # First-time setup script
└── .gitignore
```

## Development Commands

### Docker (full stack)

```bash
# First-time setup
chmod +x setup.sh && ./setup.sh

# Build and start
docker compose up -d --build

# View logs
docker compose logs -f tubevault-backend

# Restart
docker compose restart

# Stop
docker compose down
```

### Frontend development

```bash
cd frontend
npm install
npm run dev          # Vite dev server on http://localhost:5173
npm run build        # Production build to dist/
npm run preview      # Preview production build
npm run test         # Run vitest (one-shot)
npm run test:watch   # Run vitest in watch mode
```

### Backend development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8031 --reload
```

API docs available at `http://localhost:8031/docs` (Swagger) and `/redoc`.

## Architecture Details

### Backend

- **Framework:** FastAPI with async handlers, CORS open to all origins
- **Database:** SQLite via aiosqlite (schema version 28), two databases:
  - `tubevault.db` - Main database (videos, playlists, categories, subscriptions, etc.)
  - `scan_index.db` - Scan/index database for local video discovery
- **Router pattern:** Each router uses `APIRouter(prefix="/api/{resource}", tags=["Resource"])` and is registered in `main.py`
- **Background tasks:** Managed by `TaskManager` - RSS cron (5 min), drip-feed cron (15 min), thumbnail/banner backfill
- **Services:** Business logic lives in `app/services/` - download_service, rss_service, job_service, etc.
- **WebSockets:** Three WS endpoints for real-time updates:
  - `/api/jobs/ws` - Activity stream
  - `/api/downloads/ws` - Download progress
  - `/api/system/ws/logs` - Live log streaming
- **Entry point:** `entrypoint.sh` -> `uvicorn app.main:app` (single worker)

### Frontend

- **Framework:** Svelte 5 with `$state`, `$derived`, `$effect` runes
- **Routing:** Custom SPA router using `history.pushState()` (not page.js despite it being a dependency). URL is single source of truth. Route definitions in `src/lib/router/routes.js`
- **State management:** Svelte stores (`src/lib/stores/`). No external state library
- **API client:** Centralized in `src/lib/api/client.js` with 150+ methods organized by domain
- **Styling:** Vanilla CSS with a theme system (27 CSS variables for light/dark mode). Global styles in `src/lib/styles/global.css`
- **Testing:** Vitest with jsdom. Test files in `src/tests/`. Setup mocks localStorage, fetch, WebSocket

### Ports

| Service | Port | Description |
|---------|------|-------------|
| Backend API | 8031 | FastAPI (Swagger at /docs) |
| Frontend | 8032 | Nginx serving SPA, proxying /api/* to backend |
| Vite Dev | 5173 | Development only, proxies /api/* to :8031 |

### Data directories (mounted as Docker volumes)

All under `./data/` (gitignored): `db/`, `videos/`, `audio/`, `thumbnails/`, `avatars/`, `metadata/`, `banners/`, `subtitles/`, `exports/`, `temp/`, `rss_thumbs/`, `texts/`, `scan/`, `backups/`

## Key Database Tables

| Table | Purpose |
|-------|---------|
| `videos` | All videos (YouTube + local), status, metadata, file paths |
| `streams` | Separate audio/video stream tracks per video |
| `chapters` | YouTube chapters + manually created markers |
| `ad_markers` | SponsorBlock ad markers |
| `favorites` | Videos in named favorite lists |
| `categories` | Hierarchical categories (parent_id) |
| `video_categories` | M:N video-category mapping |
| `playlists` / `playlist_videos` | Playlists with ordered videos |
| `subscriptions` | YouTube channel subscriptions with RSS config |
| `rss_entries` | Discovered videos from RSS feeds |
| `watch_history` | Playback history with positions |
| `jobs` | Unified job queue (downloads, scans, etc.) |
| `archives` | External storage mount points |
| `settings` | Key-value app settings |
| `schema_version` | Database migration tracking |

## Coding Conventions

### Backend (Python)

- Async throughout (`async def` for all route handlers and service methods)
- Raw SQL queries via aiosqlite (no ORM). Parameterized queries with `?` placeholders
- Pydantic models for request/response validation in `app/models/`
- German comments and log messages throughout the codebase
- Logging via Python `logging` module. Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- No test framework currently set up for backend
- Schema migrations handled inline in `database.py` with version checks

### Frontend (JavaScript/Svelte)

- Svelte 5 runes syntax (`$state`, `$derived`, `$effect`) - not legacy `$:` reactive syntax
- Component files use `.svelte` extension
- JavaScript (not TypeScript)
- German UI text throughout (labels, messages, dates formatted as dd.mm.yyyy)
- Utility functions for German-locale formatting in `src/lib/utils/format.js` (e.g., "vor 5 Min.", "1.2 Mio.")
- Tests use vitest with jsdom environment

### General

- Version numbers kept in sync: `backend/app/config.py` (`VERSION`), `frontend/package.json` (`version`)
- Docker Compose orchestrates both services on a shared `tubevault-net` bridge network
- Environment variables configured via `.env` (copied from `.env.example` during setup)
- Copyright headers: `© HalloWelt42 - Private Nutzung` appear in most files

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TUBEVAULT_BACKEND_PORT` | `8031` | Backend API port |
| `TUBEVAULT_FRONTEND_PORT` | `8032` | Frontend web UI port |
| `MAX_CONCURRENT_DOWNLOADS` | `1` | Concurrent download limit |
| `DEFAULT_QUALITY` | `720p` | Default video quality (360p/480p/720p/1080p/best) |

## Important Notes for AI Assistants

1. **Language:** The codebase uses German for comments, UI text, log messages, and variable naming in some places. Maintain this convention when making changes.
2. **No ORM:** Database access is raw SQL. Always use parameterized queries to prevent SQL injection.
3. **Svelte 5 runes:** Use `$state`, `$derived`, `$effect` - NOT the legacy `$:` reactive syntax.
4. **Single worker:** The backend runs with a single uvicorn worker. Background tasks use asyncio, not multiprocessing.
5. **SQLite:** No concurrent write support concerns since single-worker, but use aiosqlite for non-blocking I/O.
6. **Docker-first:** The app is designed to run in Docker. Paths inside containers differ from host paths (`/app/data/` vs `./data/`).
7. **No TypeScript:** The frontend uses plain JavaScript. Do not introduce TypeScript.
8. **Testing:** Frontend tests exist in `frontend/src/tests/`. Run with `npm run test` from the `frontend/` directory. No backend tests currently exist.
9. **API prefix:** All backend routes are prefixed with `/api/`. The frontend Nginx config proxies `/api/*` to the backend container.
10. **Non-commercial license:** Do not add dependencies with incompatible licenses.
