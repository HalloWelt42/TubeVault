# TubeVault – Architektur-Regeln

Fixiertes Regelwerk. Gilt für alle Änderungen am Projekt.

## Stack (Stand v2.4+)

| Schicht | Technik | Container | Port |
|---|---|---|---|
| Frontend | Svelte 5 + Nginx | `tubevault-frontend` | 8032 |
| Backend | FastAPI + SQLite (aiosqlite + WAL) + FFmpeg | `tubevault-backend` | 8031 |
| POT-Provider | brainicism/bgutil-ytdlp-pot-provider | `tubevault-pot` | 4416 (intern) |
| JS-Runtime | Deno (im Backend-Dockerfile) | — | — |

## Datenlage

- DB: `/mnt/data/tubevault/db/tubevault.db` (NVMe)
- Medien: `/mnt/tb26/tubevault/{videos,audio,subtitles,exports,texts}` (USB 30 TB)
- Metadaten-Caches: NVMe (`thumbnails`, `avatars`, `metadata`, `banners`)
- Config/Cookies: `./config/` (Repo-relativ → Container `/app/config/`)

## Regeln

### R1 — DB ist Index, Dokumente sind Files
Text-artige Daten (Beschreibungen, Kapitel, Notes, Tags, Lyrics) liegen als Datei mit Schema `<video_id>.<kind>.<ext>` unter `/app/data/texts/`. Die DB-Tabelle `text_files` enthält nur Referenz (path, sha256, size, synced_at). Bei DB-Verlust sind Files die Quelle der Wahrheit.

### R2 — API-First
Vor jedem neuen Feature/Endpoint erst die vorhandene API, Libraries und DB prüfen. Oft reicht eine Erweiterung (zusätzlicher Query-Param, bestehendes Feld neu nutzen) statt Neu-Implementation.

### R3 — Saubere Architektur
- Keine Redundanz: gleiches Rendering/Logik nur einmal, extrahieren statt kopieren
- OOP-Disziplin: klare Einzelverantwortung pro Klasse/Modul
- Keine toter Code nach Refactors
- Klare Schnittstellen (WS-Events, API, Service-Methoden)
- Datenfluss explizit (Props/Events/Stores) — nicht via globalem State

### R4 — Tests als Safety-Net
Kritische Logik wird vor jedem Refactor mit pytest abgedeckt. Tests sichern das IST-Verhalten ab.
- `backend/pytest.ini`, `backend/tests/`, `backend/conftest.py`
- `make test` im `backend/` (synct App in Container, läuft pytest)
- Pure Funktionen werden extrahiert (`error_classifier.py`, `throttle_calc.py`), damit sie ohne I/O testbar sind
- `xfail` für bekannte Bugs (dokumentiert, später gefixt)
- Commit erst bei grünem `make test`

### R5 — Bundle-Verifikation
Nach jedem Frontend-Rebuild prüfen:
```bash
BUNDLE=$(curl -s http://localhost:8032/ | grep -oE 'assets/index-[^"]+\.js' | head -1)
curl -s "http://localhost:8032/$BUNDLE" | grep -oE '"2\.[0-9]+\.[0-9]+"' | head -1
```
Wenn alte Version: `docker compose build --no-cache tubevault-frontend`.

### R6 — Deutsche User-Texte
Alle user-sichtbaren Texte auf Deutsch. Tech-Englisch wie "fix-stale", "purge" vermeiden. Intern (Keys, Code, Logs) bleibt Englisch ok.

### R7 — Kein AI-Assistent-Branding im Repo
Pre-Commit-Hook blockiert bestimmte AI-Assistent-Namen in Dateien (Code, Commit-Messages, Git-Config). Absolute Regel. Siehe `.githooks/pre-commit` für die konkrete Keyword-Liste.

### R8 — Cooldown/Throttle (Anti-Bot)
- Minimum 5s zwischen Downloads (Clamp im Endpoint)
- Standard 30s
- Exponentieller Backoff bei Bot/Throttle: 30 → 60 → … → 7200 (2h)
- Throttle: `realtime` (aus Video-Länge) oder `fixed` (KB/s) — per UI in `/downloads` live einstellbar

### R9 — Versionierung
- Backend: VERSION in `app/config.py` + Docstring jeder Datei (`# v1.x.y`)
- Frontend: `package.json` → Vite `__APP_VERSION__`
- Nach jedem fachlichen Commit Version bumpen (Patch bei Fix, Minor bei Feature)

### R10 — Git-Workflow
- Arbeits-Branch: `dev`
- Jeder Commit grüne Tests + Bundle verifiziert
- Commit-Message-Stil: `v2.x.y - Titel\n\nKontext, Fix-Details, betroffene Module`
- `git push origin dev` nach jedem Commit (kein Stapeln)

## Verantwortungs-Matrix (Backend-Services)

| Modul | Zuständig für |
|---|---|
| `app/database.py` | aiosqlite Singleton, Schema-Migrationen, Indexe |
| `app/services/download_service.py` | Queue-Loop, Download-Lifecycle, Cooldown, Retries |
| `app/services/error_classifier.py` | Fehler-Kategorisierung (pure) |
| `app/services/throttle_calc.py` | Ratelimit-Berechnung (pure) |
| `app/services/rss_service.py` | RSS-Poll, Auto-Download-Entscheidung |
| `app/services/job_service.py` | zentraler Job-Status-Writer |
| `app/utils/ytdlp_adapter.py` | yt-dlp-API gekapselt (pytubefix-kompatibel) |
| `app/constants.py` | Settings-Keys + Defaults (zentrale Konstanten) |
| `app/routers/*.py` | FastAPI-Routes, dünne HTTP-Layer |

## Grenzen / Nicht-Ziele

- Kein Auth (LAN-only, privat)
- Keine Multi-User-Trennung
- Kein CSRF-Schutz (privat)
- Kein Realtime-Transkodierung (Videos werden gespeichert wie heruntergeladen)
