# TubeVault

**Selbstgehostetes YouTube-Archiv- & Streaming-System** für den Raspberry Pi 5.

Version 2.11.0 · © HalloWelt42 – Private Nutzung

## Funktionen

- **Abo-Feed per RSS** — Tabs (Aktiv / Später / Weggelegt / Ausgeblendet), Datum-Gruppierung,
  Typ-/Kanal-/Dauer-Filter, Batch-Aktionen, interner Scheduler mit schonenden Häppchen-Scans
- **Downloads über yt-dlp** — Anti-Bot-Strategie mit POT-Provider, Client-Rotation und
  optionalen Cookies; Warteschlange mit Prioritäten, Retry-Logik und einstellbarem Cooldown
- **Bibliothek & Archiv** — Infinite Scroll überall, Tag- und Mehrfach-Filter (Typ/Kanal/
  Kategorie/Musik), Sortierung, Auswahl-Modus mit Batch-Aktionen, Filter bleiben gemerkt
- **Suche** — lokal (Volltext) und auf YouTube (Videos, Shorts, Playlists, Kanäle) mit
  Nachladen und Duplikat-Filterung; zentrale Schnellsuche mit Bereichs-Filtern
- **Player** — Kapitel, Werbe-Marker (SponsorBlock), Untertitel live, Lyrics, Notizen
  (Markdown); Seiten-Panels einklappbar mit gemerktem Zustand; Tab-Gedächtnis pro Video;
  Playlist-Queue mit Sidebar; Video-/Audio-Download direkt aus dem Player
- **Eigene Videos** — Import und Scan lokaler Bestände (info.json/NFO als Goldstandard),
  Staging-Bereich, eigener Scan-Index
- **Meta-Redundanz** — `info.json` neben jedem Video (bei jeder Änderung aktuell gehalten),
  täglicher Nutzerdaten-Export als JSONL (Favoriten, Verlauf, Playlists, Kategorien, Abos …)
  und kompletter **Offline-Wiederaufbau** der Datenbank aus den Dateien (Admin → Wiederaufbau,
  mit Probelauf)
- **Datensicherheit** — wöchentliches DB-Backup (VACUUM INTO) mit Rotation und
  Integritäts-Check, DB-Identitäts-Audit beim Start
- **Live-Log-Terminal** — WebSocket-Stream mit aufklappbaren Tracebacks, Tageswechsel-Markern,
  Pause-Puffer und Job-/Dienst-Monitor
- Außerdem: Kategorien, Playlists, Favoriten, Verlauf mit „Weiterschauen", Statistiken,
  Thumbnail-Werkzeuge, Kanal-Detailseiten mit Scan und Fehlbestands-Download

## Stack

| Schicht | Technik |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLite (aiosqlite) · FFmpeg · yt-dlp |
| Frontend | Svelte 5 (Runes) · Vite · Nginx |
| Anti-Bot | bgutil-POT-Provider (eigener Container) · Deno für Challenge-Solver |
| Deployment | Docker Compose · Ports 8031 (API) / 8032 (Web) |

Zielplattform ist ein Raspberry Pi 5 (ARM64); läuft aber überall, wo Docker läuft.

## Schnellstart

```bash
docker compose up -d --build

# Web-Oberfläche:  http://<host>:8032
# API-Doku:        http://<host>:8031/docs
```

## Speicher-Layout (zwei Platten)

TubeVault trennt Index und Medien bewusst:

- **Index/Metadaten** (DB, Thumbnails, Avatare, Texte) → schnelle Platte,
  z. B. `/mnt/data/tubevault/data`
- **Medien** (Videos, Audio, Untertitel, Exporte/Backups) → große Platte,
  z. B. `/mnt/tb26/tubevault`

Die Pfade werden über die Volumes in `docker-compose.yml` gesetzt (Feinsteuerung per
`TUBEVAULT_*`-Umgebungsvariablen möglich). Die Datenbank ist nur der Index — Dokumente
(Beschreibungen, Kapitel, Notizen) liegen als Dateien im Texte-Verzeichnis, Metadaten
redundant als `info.json` neben jedem Video.

## Tests

```bash
cd backend && make test   # pytest läuft im Backend-Container (272 Tests)
```

## Projektstruktur

```
tubevault/
├── backend/
│   ├── app/
│   │   ├── main.py         # App-Entry, Startup/Shutdown, Hintergrund-Tasks
│   │   ├── config.py       # Konfiguration + VERSION
│   │   ├── database.py     # SQLite-Schema + Migrationen
│   │   ├── routers/        # API-Endpunkte
│   │   ├── services/       # Business-Logik (Downloads, RSS, Sidecars, Rebuild …)
│   │   └── utils/          # yt-dlp-Adapter u. a.
│   └── tests/              # pytest-Suite
├── frontend/
│   └── src/
│       ├── routes/         # Seiten (Svelte 5)
│       └── lib/            # Komponenten, Stores, listLoader, Router
├── scripts/                # Backup- und Wartungs-Skripte (Cron)
├── config/                 # Laufzeit-Konfiguration (nicht versioniert: Cookies)
└── docker-compose.yml
```

## Lizenz

Privates Projekt, siehe [LICENSE](LICENSE).
