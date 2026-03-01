# WORKFLOWS.md — TubeVault Workflow-Dokumentation

Vollständige Übersicht aller Workflows in TubeVault v1.9.13.

---

## Inhaltsverzeichnis

1. [Video-Download](#1-video-download)
2. [Job-System](#2-job-system)
3. [RSS-Feed-Polling](#3-rss-feed-polling)
4. [Abo-Verwaltung (Subscriptions)](#4-abo-verwaltung-subscriptions)
5. [Feed-Status-Management](#5-feed-status-management)
6. [Drip-Feed (Automatischer Gradual-Download)](#6-drip-feed-automatischer-gradual-download)
7. [Kanal-Playlists (YouTube-Import)](#7-kanal-playlists-youtube-import)
8. [Lokaler Scan](#8-lokaler-scan)
9. [Import (Diverse Quellen)](#9-import-diverse-quellen)
10. [Archiv (Externe Speicher)](#10-archiv-externe-speicher)
11. [Export](#11-export)
12. [Backup & Restore](#12-backup--restore)
13. [Wiedergabe (Streaming)](#13-wiedergabe-streaming)
14. [Kapitel & Timestamps](#14-kapitel--timestamps)
15. [Ad-Marker (SponsorBlock)](#15-ad-marker-sponsorblock)
16. [Favoriten](#16-favoriten)
17. [Kategorien](#17-kategorien)
18. [Lyrics](#18-lyrics)
19. [Suche](#19-suche)
20. [Thumbnail-AI (LM Studio)](#20-thumbnail-ai-lm-studio)
21. [Video-Anreicherung (Auto-Enrich)](#21-video-anreicherung-auto-enrich)
22. [System & Cleanup](#22-system--cleanup)

---

## 1. Video-Download

**Auslöser:** `POST /api/downloads` (User klickt "Download")
**Dateien:** `download_service.py`, `routers/downloads.py`

### Ablauf

```
User klickt Download
       │
       ▼
┌─────────────────┐
│ 1. QUEUE         │  Video wird in Job-Queue eingereiht
│    job_type=     │  Qualität + Format gespeichert
│    "download"    │  Status: pending
└────────┬────────┘
         │  Semaphore (MAX_CONCURRENT_DOWNLOADS)
         ▼
┌─────────────────┐
│ 2. RESOLVE       │  pytubefix.YouTube(url) → Metadaten
│                  │  Titel, Kanal, Dauer, Thumbnail-URL
│                  │  Stream-Auswahl nach Qualität
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. DOWNLOAD      │  Video-Stream + Audio-Stream separat
│                  │  Fortschritt via WebSocket /api/downloads/ws
│                  │  Dateien: temp/{video_id}_video.mp4
│                  │           temp/{video_id}_audio.m4a
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. MERGE (FFmpeg)│  ffmpeg -i video -i audio -c copy output.mp4
│                  │  Zusammenführung von Video + Audio
│                  │  Temp-Dateien werden gelöscht
└────────┬────────┘
         ▼
┌─────────────────┐
│ 5. FINALIZE      │  Verschieben nach videos/{video_id}/
│                  │  Thumbnail herunterladen
│                  │  DB-Eintrag: status='ready'
│                  │  Tags, Metadaten, Dateigröße speichern
└─────────────────┘
```

### Beteiligte Tabellen

| Tabelle | Zweck |
|---------|-------|
| `jobs` | Job-Queue-Eintrag (Status, Fortschritt) |
| `videos` | Finaler Video-Eintrag |
| `streams` | Audio/Video-Stream-Infos |

### Fehlerbehandlung
- **Netzwerk-Fehler:** Job wird als `error` markiert, Retry möglich
- **FFmpeg-Fehler:** Temp-Dateien bleiben zur Diagnose, Status → `error`
- **Duplikat:** Prüfung ob `video_id` bereits in `videos` existiert

### WebSocket-Updates

```json
{
  "type": "download_progress",
  "video_id": "dQw4w9WgXcQ",
  "progress": 0.65,
  "speed": "2.4 MB/s",
  "eta": "12s"
}
```

---

## 2. Job-System

**Auslöser:** Wird von allen anderen Workflows genutzt
**Dateien:** `job_service.py`, `routers/jobs.py`

### Status-Flow

```
pending → running → completed
                  → failed
                  → cancelled
```

### Funktionsweise

1. **Erstellen:** Jeder Workflow erstellt einen Job mit `type`, `title`, `priority`
2. **Scheduling:** `schedule_exclusive()` — nur ein Job dieses Typs gleichzeitig
3. **Fortschritt:** `update_progress(job_id, progress, message)` → WebSocket-Broadcast
4. **Abschluss:** `complete_job(job_id)` oder `fail_job(job_id, error)`

### Job-Typen

| Typ | Workflow | Priorität |
|-----|----------|-----------|
| `download` | Video-Download | 5 |
| `rss_cycle` | RSS-Feed-Polling | 8 |
| `scan` | Lokaler Scan | 3 |
| `import` | Import (Batch) | 3 |
| `playlist_fetch` | Playlist-Videos laden | 4 |
| `playlist_import` | Playlist importieren | 4 |
| `cleanup` | System-Bereinigung | 2 |

### WebSocket-Endpunkt

`/api/jobs/ws` — Echtzeit-Updates für alle aktiven Jobs

---

## 3. RSS-Feed-Polling

**Auslöser:** Interner Cron alle 5 Minuten (`main.py`)
**Dateien:** `rss_service.py`, `routers/feed_router.py`

### Ablauf

```
5-Minuten-Cron-Tick
       │
       ▼
┌──────────────────────┐
│ 1. LOCK PRÜFEN       │  Exklusiver Lock (_polling Flag)
│                      │  Warten auf schwere Jobs (Scan, Cleanup)
│                      │  Timeout: 30 Sekunden
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 2. FÄLLIGE FEEDS     │  SQL: last_checked < now - check_interval
│    ABFRAGEN          │  Älteste zuerst, max 20 pro Tick
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 3. RSS-XML ABRUFEN   │  YouTube Atom-Feed pro Kanal
│                      │  + UUSH-Feed (Shorts)
│                      │  + UULV-Feed (Livestreams)
│                      │  → Video-Typ-Klassifikation
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 4. NEUE VIDEOS       │  INSERT in rss_entries (UNIQUE: video_id+channel_id)
│    SPEICHERN         │  Filter: max_age_days (Standard: 90 Tage)
│                      │  Thumbnails lokal cachen
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 5. INTERVALL         │  Neue Videos gefunden → Intervall zurücksetzen
│    ANPASSEN          │  Keine Videos → Intervall verdoppeln (max 7 Tage)
│                      │  404-Fehler → Aggressives Backoff (6h→12h→24h)
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 6. AUTO-DOWNLOAD     │  Falls Abo auto_download=1:
│    (optional)        │  Videos automatisch in Download-Queue
│                      │  Tageslimit: rss.auto_dl_daily_limit (Standard: 20)
└──────────────────────┘
```

### Adaptive Intervalle

| Situation | Aktion |
|-----------|--------|
| Neue Videos gefunden | Intervall → Standard (30 Min) |
| Keine neuen Videos | Intervall × 2 (max 7 Tage) |
| Feed 404 | Backoff: 6h → 12h → 24h |
| Anderer Fehler | Intervall × 2 (max 1 Tag) |

### Beteiligte Tabellen

| Tabelle | Zweck |
|---------|-------|
| `subscriptions` | Abo-Daten, Intervall, Fehlercount |
| `rss_entries` | Entdeckte Videos mit Status |
| `jobs` | Sichtbarer Job (Typ: `rss_cycle`) |

### Einstellungen (settings-Tabelle)

| Schlüssel | Standard | Beschreibung |
|-----------|----------|--------------|
| `rss.enabled` | `true` | RSS-Polling aktiv |
| `rss.interval` | `1800` | Standard-Intervall (30 Min) |
| `rss.max_age_days` | `90` | Videos älter als X Tage ignorieren |
| `rss.auto_dl_daily_limit` | `20` | Max. Auto-Downloads pro Tag |

---

## 4. Abo-Verwaltung (Subscriptions)

**Auslöser:** `POST /api/subscriptions` (User abonniert Kanal)
**Dateien:** `rss_service.py`, `routers/subscriptions.py`

### Einzelnes Abo anlegen

1. **Input-Normalisierung** — Kanal-ID, URL, @Handle → `channel_id` (UC...)
2. **RSS-Feed abrufen** — Kanalname und Link extrahieren
3. **Avatar herunterladen** — Via pytubefix (rate-limited), speichern als `avatars/{channel_id}.jpg`
4. **DB-Insert** — `INSERT OR IGNORE` in `subscriptions`
5. **Erster Poll** — Sofortiger RSS-Abruf im Hintergrund

### Batch-Import (z.B. FreeTube)

1. **Job erstellen** — Typ: `import`, Fortschritt alle 10 Items
2. **Schnell-Import** — Nur RSS (kein pytubefix), rate-limited
3. **Avatars nachladen** — Hintergrund-Task mit Resume-Fähigkeit

### Abo-Einstellungen

| Feld | Beschreibung |
|------|--------------|
| `auto_download` | Neue Videos automatisch herunterladen |
| `download_quality` | 360p / 480p / 720p / 1080p / best |
| `audio_only` | Nur Audio herunterladen |
| `drip_enabled` | Gradual-Download aktivieren |
| `drip_count` | Videos pro Drip-Zyklus |
| `check_interval` | Benutzerdefiniertes Poll-Intervall |
| `enabled` | Abo pausieren |

---

## 5. Feed-Status-Management

**Auslöser:** User-Aktionen im Feed-Tab
**Dateien:** `routers/feed_router.py`

### Status-Flow

```
                ┌──────────┐
    Neues   ──► │  active   │ ◄── restore
    Video       └────┬──┬──┘
                     │  │
            "Später" │  │ "Gelesen"
                     ▼  ▼
              ┌────────┐ ┌───────────┐
              │ later  │ │ dismissed │
              └────┬───┘ └─────┬─────┘
                   │           │
                   └─────┬─────┘
                         ▼
                   ┌───────────┐
                   │ archived  │
                   └───────────┘
```

### Filter-Optionen

- **Tab:** active / later / dismissed / archived / all
- **Kanal:** Komma-getrennte channel_ids
- **Typ:** video / short / live
- **Keywords:** Tag-basierter OR-Filter
- **Dauer:** duration_min / duration_max

### Operationen

- Einzeln: Status setzen für ein Video
- Bulk: Mehrere Videos auf einmal
- Kanal-weit: Alle Videos eines Kanals verschieben
- Alle verwerfen: Alle aktiven → dismissed

---

## 6. Drip-Feed (Automatischer Gradual-Download)

**Auslöser:** Interner Cron alle 15 Minuten (`main.py`)
**Dateien:** `main.py` (Zeilen 86-183), `rss_service.py`

### Ablauf

```
15-Minuten-Cron
       │
       ▼
┌──────────────────────┐
│ 1. FÄLLIGE ABOS      │  WHERE drip_enabled=1
│    ABFRAGEN          │  AND drip_next_run <= now
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 2. AUTO-ARCHIVIEREN  │  (falls drip_auto_archive=1)
│                      │  Alte heruntergeladene Videos → is_archived=1
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 3. BATCH BERECHNEN   │  Strategie: 2 älteste + 1 neuestes
│                      │  Nur Videos die NICHT in videos-Tabelle
│                      │  drip_count: 1-10 (typisch: 3)
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 4. DOWNLOADS QUEUEN  │  Für jedes Video:
│                      │  → download_service.add_to_queue()
│                      │  → Job erstellen (Typ: download)
└────────┬─────────────┘
         ▼
┌──────────────────────┐
│ 5. NÄCHSTEN LAUF     │  Zufällig morgen 02:00-10:00 Uhr
│    PLANEN            │  (Thundering Herd vermeiden)
│                      │  Fertig? → drip_enabled=0
└──────────────────────┘
```

### Strategie

- **2 älteste fehlende Videos** — Historischen Content nachholen
- **1 neuestes fehlendes Video** — Aktuellen Content sichern
- **Abschluss:** Wenn keine Videos mehr fehlen → Drip deaktivieren

---

## 7. Kanal-Playlists (YouTube-Import)

**Auslöser:** User öffnet Kanal-Details → "Playlists"
**Dateien:** `playlist_service.py`, `routers/channel_playlists.py`

### 3-Stufen-Prozess

```
Stufe 1: Playlists laden          Stufe 2: Videos laden          Stufe 3: Importieren
POST .../fetch-playlists    →     POST .../fetch-videos    →    POST .../import
       │                                 │                             │
       ▼                                 ▼                             ▼
pytubefix.Channel.playlists     pytubefix.Playlist.video_urls    Lokale Playlist
       │                                 │                       erstellen
       ▼                                 ▼                             │
channel_playlists Tabelle        video_ids als JSON Array         playlists +
(playlist_id, title, ...)        in channel_playlists             playlist_videos
```

### Beteiligte Tabellen

| Tabelle | Zweck |
|---------|-------|
| `channel_playlists` | YouTube-Playlist-Metadaten + Video-IDs |
| `playlists` | Lokale Playlist (source='youtube') |
| `playlist_videos` | Video-Zuordnung mit Position |

---

## 8. Lokaler Scan

**Auslöser:** `POST /api/scan/start` (User scannt Verzeichnis)
**Dateien:** `scan_service.py`, `routers/scan.py`

### Ablauf

```
Phase 1: DISCOVERY (Automatisch)               Phase 2: REGISTRIERUNG (Manuell)
┌─────────────────────────────────┐            ┌──────────────────────────────┐
│ Verzeichnis rekursiv scannen    │            │ User wählt Einträge aus      │
│ Filter: .mp4, .mkv, .webm, ... │            │ POST /api/scan/register      │
│         .avi, .mov, .m4v, ...   │            │                              │
│                                 │            │ → Datei kopieren nach        │
│ YouTube-ID aus Dateiname:       │            │   videos/{video_id}/         │
│   [dQw4w9WgXcQ]                │            │                              │
│   (dQw4w9WgXcQ)                │            │ → ffprobe: Dauer, Auflösung  │
│                                 │            │                              │
│ Begleitdateien erkennen:        │            │ → Thumbnail: YouTube > lokal │
│   .nfo, .srt, .vtt, Thumbs     │            │   > ffmpeg (5-Sek-Frame)     │
│                                 │            │                              │
│ → INSERT in scan_index          │            │ → INSERT in videos           │
│   (separate scan_db)            │            │   status='ready'             │
└─────────────────────────────────┘            └──────────────────────────────┘
```

### Duplikat-Erkennung
- YouTube-ID bereits in `videos` → Status `duplicate`
- Pfad bereits in `scan_index` → Übersprungen

### Beteiligte Datenbanken

| Datenbank | Tabelle | Zweck |
|-----------|---------|-------|
| `scan_index.db` | `scan_index` | Temporärer Discovery-Index |
| `scan_index.db` | `scan_state` | Scan-Pfad + Optionen |
| `tubevault.db` | `videos` | Finaler Video-Eintrag |

---

## 9. Import (Diverse Quellen)

**Auslöser:** Verschiedene `POST /api/import/*` Endpunkte
**Dateien:** `import_service.py`, `routers/imports.py`

### Quellen-Übersicht

| Quelle | Endpunkt | Methode |
|--------|----------|---------|
| YouTube-Playlist | `/api/import/youtube-playlist` | pytubefix |
| URL-Liste | `/api/import/url-list` | Batch-Download |
| Kanal-Videos | `/api/import/channel-videos/{id}` | pytubefix |
| Lokale Datei | `/api/import/local-video` | Dateisystem |
| Verzeichnis-Scan | `/api/import/scan-directory` | Fuzzy-Matching |
| FreeTube Abos | `/api/import/freetube/subscriptions` | JSONL-Parser |
| FreeTube Playlists | `/api/import/freetube/playlists` | JSONL-Parser |
| YouTube Takeout | `/api/import/youtube-takeout/*` | JSON/CSV-Parser |

### Smart Directory Scan (Fuzzy-Matching)

```
Verzeichnis scannen
       │
       ▼
┌──────────────────────────┐
│ 1. DATEIEN ENTDECKEN     │  os.walk() + Video-Extension-Filter
│                          │  YouTube-ID aus Dateiname extrahieren
│                          │  Begleitdateien erkennen (.nfo, .srt)
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 2. MATCHING              │  Priorität 1: Exakte YouTube-ID
│                          │  Priorität 2: Fuzzy Titel-Match (RSS)
│                          │  Priorität 3: Dauer-Verifikation
│                          │
│  Match-Typen:            │
│  exact, exact_rss,       │
│  fuzzy_hi, fuzzy_lo,     │
│  weak, none, duplicate   │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 3. STAGING               │  Ergebnisse in scan_staging
│                          │  User reviewed + entscheidet
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 4. ENTSCHEIDUNGEN        │  link      → Mit bestehendem Video verknüpfen
│    AUSFÜHREN             │  link_rss  → Mit RSS-Eintrag verknüpfen
│                          │  import_new → Als neues Video importieren
│                          │  skip      → Ignorieren
│                          │  replace   → Bestehende Datei ersetzen
│                          │  delete    → Datei löschen
└──────────────────────────┘
```

### Beteiligte Tabellen

| Tabelle | Zweck |
|---------|-------|
| `scan_sessions` | Async Scan-Sitzungen |
| `scan_staging` | Temporäre Ergebnisse mit Entscheidungen |
| `videos` | Finaler Import |
| `playlists` | Playlist-Importe |
| `subscriptions` | Abo-Importe (FreeTube/Takeout) |
| `watch_history` | Takeout-Wiedergabehistorie |

---

## 10. Archiv (Externe Speicher)

**Auslöser:** `POST /api/archives` (User fügt Archiv hinzu)
**Dateien:** `archive_service.py`, `routers/archives.py`

### Ablauf

```
┌────────────────────────────┐
│ 1. ARCHIV REGISTRIEREN     │  Pfad + Name + Optionen
│    POST /api/archives      │  Prüfung: Pfad existiert + lesbar
└────────┬───────────────────┘
         ▼
┌────────────────────────────┐
│ 2. MOUNT-WATCHER           │  Hintergrund-Loop (alle 30 Sek)
│    (automatisch)           │  Prüft: Pfad erreichbar?
│                            │  offline → online: Auto-Scan starten
└────────┬───────────────────┘
         ▼
┌────────────────────────────┐
│ 3. ARCHIV SCANNEN          │  Glob-Patterns: *.mp4, *.mkv, ...
│    POST .../scan           │  YouTube-ID aus Dateiname oder ffprobe
│                            │  → INSERT in video_archives
│                            │  → videos-Tabelle aktualisieren
└────────┬───────────────────┘
         ▼
┌────────────────────────────┐
│ 4. PFAD-AUFLÖSUNG          │  Beim Abspielen:
│    resolve_video_path()    │  1. Lokale Kopie? → videos/{id}/
│                            │  2. Archiv? → video_archives Pfad
│                            │  3. Archiv mounted? → Prüfen
└────────────────────────────┘
```

### Storage-Typen

| Typ | Bedeutung |
|-----|-----------|
| `local` | Datei auf internem Speicher |
| `archive` | Datei nur auf externem Archiv |
| `both` | Kopie auf beiden Speicherorten |
| `archived_offline` | Archiv bekannt, aber nicht gemountet |

### Beteiligte Tabellen

| Tabelle | Zweck |
|---------|-------|
| `archives` | Archiv-Metadaten (Pfad, Auto-Scan, Status) |
| `video_archives` | Mapping: video_id → Archiv-Pfad |
| `videos` | storage_type, archive_id |

---

## 11. Export

**Auslöser:** User klickt Export-Button
**Dateien:** `routers/exports.py`

### Export-Formate

| Endpunkt | Format | Inhalt |
|----------|--------|--------|
| `GET /api/exports/videos/json` | JSON | Alle fertigen Videos mit Metadaten |
| `GET /api/exports/videos/csv` | CSV (UTF-8 BOM) | Video-Metadaten für Excel |
| `GET /api/exports/subscriptions/csv` | CSV | Abo-Liste (FreeTube-kompatibel) |
| `GET /api/exports/playlists/json` | JSON | Playlists mit Videos und Positionen |

### Besonderheiten
- **Streaming-Response** — Kein Disk-Write nötig
- **UTF-8 BOM** — CSV mit BOM für korrekte Excel-Darstellung
- **Dateiname:** `tubevault-{typ}-YYYYMMDD.{ext}`
- **Sensible Daten:** ai_summary und ai_tags werden entfernt

---

## 12. Backup & Restore

**Auslöser:** `POST /api/backup/create` oder `/restore`
**Dateien:** `routers/backup.py`

### Backup erstellen

```
POST /api/backup/create
       │
       ▼
┌──────────────────────────┐
│ Methode 1: VACUUM INTO   │  Konsistente Kopie ohne WAL
│ (bevorzugt)              │  Atomar auf Dateisystem-Ebene
└────────┬─────────────────┘
         │ Falls Fehler ↓
┌──────────────────────────┐
│ Methode 2: Fallback      │  WAL-Checkpoint (TRUNCATE)
│                          │  + shutil.copy2()
└────────┬─────────────────┘
         ▼
Dateiname: tubevault_backup_YYYYMMDD_HHMMSS_beX-Y-Z_feX-Y-Z.db
Speicherort: exports/backups/
```

### Restore

```
POST /api/backup/restore/{filename}
       │
       ▼
┌──────────────────────────┐
│ 1. SAFETY-BACKUP         │  Aktuellen Stand sichern als
│                          │  tubevault_pre_restore_YYYYMMDD.db
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 2. RESTORE               │  DB-Verbindung trennen
│                          │  WAL-Dateien löschen
│                          │  Backup → aktive DB kopieren
│                          │  Neu verbinden + Schema initialisieren
└────────┬─────────────────┘
         │ Falls Fehler ↓
┌──────────────────────────┐
│ 3. ROLLBACK              │  Safety-Backup wiederherstellen
└──────────────────────────┘
```

### Upload-Restore
- `POST /api/backup/restore-upload` mit Datei-Upload
- Validierung: `.db`-Extension, SQLite-Magic-Number, min. 100 Bytes
- Pfad-Traversal-Schutz: `..`, `/`, `\` blockiert

---

## 13. Wiedergabe (Streaming)

**Auslöser:** User öffnet Video im Player
**Dateien:** `routers/player.py`, `archive_service.py`

### Ablauf

```
GET /api/player/{video_id}
       │
       ▼
┌──────────────────────────┐
│ 1. PFAD AUFLÖSEN         │  videos-Tabelle → file_path
│                          │  Falls Archiv → archive_service
│                          │  Prüfung: Datei existiert?
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 2. RANGE REQUEST         │  HTTP Range-Header parsen
│                          │  Partial Content (206)
│                          │  Chunk-Größe: 1 MB
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 3. STREAMING             │  StreamingResponse mit Chunks
│                          │  Content-Range Header
│                          │  Seek, Pause, Skip unterstützt
└──────────────────────────┘
```

### Weitere Player-Endpunkte

| Endpunkt | Funktion |
|----------|----------|
| `GET /{id}/stream/{stream_id}` | Spezifischen Audio/Video-Stream abspielen |
| `GET /{id}/thumbnail` | Thumbnail mit 24h Cache |
| `GET /{id}/subtitles` | Verfügbare Untertitel auflisten |
| `GET /{id}/subtitle/{file}` | Untertitel-Datei laden |
| `POST /{id}/subtitles/download` | Untertitel von YouTube herunterladen |
| `POST /{id}/audio/extract` | Audio-Spur extrahieren (FFmpeg) |
| `GET /{id}/audio` | Extrahierte Audio-Datei laden |

### Thumbnail-Fallback-Kette
1. `videos.thumbnail_path` (DB-Pfad)
2. `thumbnails/{video_id}/thumbnail.jpg` (Nested)
3. `thumbnails/{video_id}.*` (Flat, jpg/png/webp)

---

## 14. Kapitel & Timestamps

**Auslöser:** User oder automatisch (YouTube-Fetch)
**Dateien:** `routers/chapters.py`

### Manuelles Kapitel erstellen
- `POST /api/chapters/{video_id}` mit title, start_time, end_time
- Quelle: `source='manual'`

### YouTube-Kapitel abrufen
1. Rate-Limit prüfen (`pytubefix`)
2. YouTube-ID validieren (11 Zeichen, kein `local_*`)
3. `pytubefix.YouTube.chapters` via Thread-Executor
4. Alte YouTube-Kapitel löschen
5. Neue Kapitel einfügen mit `source='youtube'`

### Kapitel-Thumbnails generieren
- FFmpeg: Frame bei `start_time + 2` Sekunden extrahieren
- Speichern: `chapter_thumbs/{video_id}/{chapter_id}.jpg`
- Bulk-Regeneration für alle Videos mit Kapiteln möglich

### Tabelle: `chapters`

| Spalte | Beschreibung |
|--------|--------------|
| `video_id` | Zugehöriges Video |
| `title` | Kapitelname |
| `start_time` | Startzeit (Sekunden) |
| `end_time` | Endzeit (Sekunden) |
| `source` | `youtube` oder `manual` |
| `thumbnail_url` | Pfad zum Kapitel-Thumbnail |

---

## 15. Ad-Marker (SponsorBlock)

**Auslöser:** User oder automatisch (Auto-Enrich)
**Dateien:** `routers/ad_markers.py`

### SponsorBlock-Import

1. API-Aufruf: `GET {SB_API}/api/skipSegments?videoID={id}&categories=[...]`
2. Antwort parsen: Segmente mit UUID, Kategorie, Zeitbereich, Votes
3. Duplikate prüfen via `sb_uuid`
4. Einfügen mit `source='sponsorblock'`

### Kategorie-Mapping

| SponsorBlock | Deutsch |
|--------------|---------|
| `sponsor` | Sponsor |
| `selfpromo` | Eigenwerbung |
| `intro` | Intro |
| `outro` | Outro |
| `interaction` | Interaktion |

### Tabelle: `ad_markers`

| Spalte | Beschreibung |
|--------|--------------|
| `video_id` | Zugehöriges Video |
| `start_time` | Startzeit |
| `end_time` | Endzeit |
| `label` | Beschriftung |
| `source` | `manual` oder `sponsorblock` |
| `category` | SB-Kategorie |
| `sb_uuid` | SponsorBlock-UUID (Duplikat-Schutz) |

---

## 16. Favoriten

**Auslöser:** User-Aktion (Herz-Icon)
**Dateien:** `routers/favorites.py`

### Funktionsweise

- **Listen sind implizit** — Entstehen beim ersten Hinzufügen eines Videos
- **Multi-Listen:** Ein Video kann in mehreren Listen sein
- **Position-basiert:** Manuelle Sortierung über `position`-Feld

### Operationen

| Endpunkt | Funktion |
|----------|----------|
| `GET /api/favorites` | Alle Favoriten (optional nach Liste filtern) |
| `GET /api/favorites/lists` | Alle Listennamen + Anzahl |
| `POST /api/favorites` | Video zu Liste hinzufügen |
| `PUT /api/favorites/reorder` | Reihenfolge ändern |
| `GET /api/favorites/check/{id}` | In welchen Listen ist das Video? |

### Tabelle: `favorites`

| Spalte | Beschreibung |
|--------|--------------|
| `video_id` | Video-Referenz |
| `list_name` | Listenname (implizit erstellt) |
| `position` | Sortier-Position |
| `added_at` | Zeitstempel |

---

## 17. Kategorien

**Auslöser:** User-Aktion (Kategorisierung)
**Dateien:** `routers/categories.py`

### Funktionsweise

- **Hierarchisch** (parent_id vorhanden, aber aktuell flach genutzt)
- **M:N-Beziehung** — Ein Video kann mehrere Kategorien haben
- **Farbcodiert** — Jede Kategorie hat eine Farbe (hex)

### Besondere Operationen

| Endpunkt | Funktion |
|----------|----------|
| `POST /api/categories/{id}/auto-assign` | Bulk-Zuordnung nach Kanal/Keyword |
| `POST /api/categories/quick-channel-assign` | Kategorie für ganzen Kanal erstellen |
| `POST /api/categories/quick-channel-assign-all` | Alle unzugeordneten Videos nach Kanal gruppieren |
| `POST /api/categories/cleanup-orphans` | Verwaiste Zuordnungen entfernen |

### Tabellen

| Tabelle | Zweck |
|---------|-------|
| `categories` | name, description, color, icon, sort_order |
| `video_categories` | video_id ↔ category_id (M:N) |

---

## 18. Lyrics

**Auslöser:** User öffnet Lyrics-Tab
**Dateien:** `lyrics_service.py`, `routers/lyrics.py`

### Ablauf

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ 1. ERKENNUNG    │ ──► │ 2. SUCHE     │ ──► │ 3. AUSWAHL  │
│ Ist es Musik?   │     │ ytmusic oder │     │ Passende    │
│ Artist + Titel  │     │ LRCLIB       │     │ Version     │
│ aus Video-Titel │     │              │     │ auswählen   │
└─────────────────┘     └──────────────┘     └─────────────┘
```

### Quellen

| Quelle | Beschreibung |
|--------|--------------|
| YouTube Music | Primäre Suche |
| LRCLIB | Crowdsourced-Datenbank (mit Versionsauswahl) |
| Untertitel | VTT → LRC Konvertierung |
| Manuell | User-Upload (Plain/Synced LRC) |

### Dual-Track-System
- **plain.txt** — Reiner Text ohne Zeitstempel
- **synced.lrc** — Zeitgestempelte Lyrics (für Karaoke-Darstellung)

### Offset-Korrektur
- `POST /{video_id}/offset` — Millisekunden-Offset für Sync-Anpassung

---

## 19. Suche

**Auslöser:** User gibt Suchbegriff ein
**Dateien:** `routers/search.py`

### URL-Auflösung

```
POST /api/search/resolve-url
       │
       ▼
┌──────────────────────────┐
│ URL-Typ erkennen:        │
│ • Video (11-Zeichen-ID)  │  → Video-Info + Download-Status
│ • Playlist (list=...)    │  → Alle Videos + Owner
│ • Kanal (@handle, /c/)   │  → Kanal-Metadaten
└──────────────────────────┘
```

### YouTube-Suche

- `GET /api/search/youtube/full` — Videos, Shorts, Playlists, Kanäle
- `GET /api/search/youtube` — Nur Videos
- Rate-Limited via `rate_limiter.acquire("pytubefix")`
- **Anreicherung:** Für jedes Ergebnis prüfen ob `already_downloaded` oder `already_in_queue`

### Lokale Suche

- `GET /api/search/local` — Volltextsuche in title, channel_name, description, tags
- Filter: source (youtube/local/imported), scope (favorites/playlists/own)
- Sortierung: play_count DESC (meistgespielte zuerst)

---

## 20. Thumbnail-AI (LM Studio)

**Auslöser:** User startet AI-Analyse
**Dateien:** `thumbnail_ai_service.py`, `routers/thumbnail_ai.py`

### Voraussetzung
- Externer LM Studio Server mit Vision-Modell (lokal oder Netzwerk)

### Ablauf

```
┌──────────────────────────┐
│ 1. VERBINDUNG TESTEN     │  GET {lm_studio_url}/api/models
│    POST /test-connection │  → Modell-Liste zurück
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 2. QUEUE STARTEN         │  POST /api/thumbnail-ai/run
│                          │  Findet alle Videos ohne ai_analysis
│                          │  Startet Hintergrund-Task
└────────┬─────────────────┘
         ▼  (für jedes Video)
┌──────────────────────────┐
│ 3. ANALYSE               │  Thumbnail laden + resizen
│                          │  POST an LM Studio Vision-Endpoint
│                          │  Antwort: Labels, Summary, Typ
│                          │  → videos.ai_analysis (JSON)
└──────────────────────────┘
```

### Queue-Management

| Endpunkt | Funktion |
|----------|----------|
| `POST /api/thumbnail-ai/run` | Queue-Verarbeitung starten |
| `POST /api/thumbnail-ai/stop` | Verarbeitung stoppen |
| `POST /api/thumbnail-ai/queue/reset-all` | Alle Analysen zurücksetzen |
| `POST /api/thumbnail-ai/queue/reset-errors` | Nur Fehler zurücksetzen |

### Konfiguration
- Prompt anpassbar (`GET/PUT /api/thumbnail-ai/prompt`)
- Temperature + max_tokens konfigurierbar
- Bildgröße: max 2048px (Standard)

---

## 21. Video-Anreicherung (Auto-Enrich)

**Auslöser:** `POST /api/videos/{id}/auto-enrich`
**Dateien:** `routers/videos.py`

### Ablauf

Prüft `enrichment_log` für jeden Typ — wiederholt Erfolge nicht, wartet 24h nach Fehlern.

```
┌─────────────────────┐
│ SponsorBlock-Marker  │  Falls keine vorhanden → importieren
├─────────────────────┤
│ YouTube-Kapitel      │  Falls keine vorhanden → abrufen
├─────────────────────┤
│ Kapitel-Thumbnails   │  Falls Kapitel + Videodatei → generieren
├─────────────────────┤
│ Untertitel           │  Falls keine → DE oder EN herunterladen
├─────────────────────┤
│ Thumbnail            │  Falls fehlt → YouTube hqdefault laden
└─────────────────────┘
```

### Enrichment-Log

| Spalte | Beschreibung |
|--------|--------------|
| `video_id` | Video-Referenz |
| `type` | sponsorblock / chapters / subtitles / thumbnail |
| `attempted_at` | Zeitstempel |
| `success` | true/false |
| `result_count` | Anzahl importierter Elemente |
| `error` | Fehlermeldung |

---

## 22. System & Cleanup

**Auslöser:** Verschiedene System-Endpunkte
**Dateien:** `routers/system.py`

### Log-System

- **Ring-Buffer:** 3000 Einträge im Speicher
- **Flush-Loop:** Alle 250ms neue Einträge via WebSocket senden
- **Kategorien:** download, rss, queue, rate, scan, import, meta, stream, lyrics, api, frontend
- **WebSocket:** `/api/system/ws/logs` — Live-Stream + letzte 100 Einträge

### Badges (Schnell-Zähler)

`GET /api/system/badges` liefert Counts für: videos, subscriptions, new_rss, active_downloads, favorites, playlists, categories, history, archives, own_videos, batch_queue

### Full Cleanup (12 Schritte)

```
POST /api/system/cleanup-full

 1. Ghost-Videos     → status='ready' aber Datei fehlt → status='ghost'
 2. Verwaiste Kategorien   → video_categories ohne gültiges Video
 3. Verwaiste Playlists    → playlist_videos ohne gültiges Video
 4. Verwaiste Favoriten    → favorites ohne gültiges Video
 5. Verwaiste Historie     → watch_history ohne gültiges Video
 6. Verwaiste Streams      → streams ohne gültiges Video
 7. Verwaiste Kapitel      → chapters ohne gültiges Video
 8. Alte Download-Jobs     → > 7 Tage, abgeschlossen/fehlerhaft
 9. Alte Jobs              → > 24h, abgeschlossen/fehlerhaft
10. Temp-Verzeichnis       → Alles in data/temp/ löschen
11. Verwaiste Thumbnails   → Dateien ohne zugehöriges Video
12. VACUUM                 → SQLite-Datenbank komprimieren
```

### Hintergrund-Tasks

| Endpunkt | Funktion |
|----------|----------|
| `GET /api/system/tasks` | Liste aller Hintergrund-Tasks |
| `POST /api/system/tasks/{name}/stop` | Task stoppen |
| `POST /api/system/tasks/{name}/start` | Task starten |
| `POST /api/system/tasks/{name}/restart` | Task neustarten |

### Health & Status

| Endpunkt | Inhalt |
|----------|--------|
| `GET /api/system/health` | Einfacher Health-Check |
| `GET /api/system/version` | App-Version |
| `GET /api/system/stats` | Video-Stats, Disk-Usage, DB-Größe, Queue-Counts |
| `GET /api/system/status` | Rate-Limiter, RSS-Worker, Download-Queue, Jobs, RYD-API, Schema-Version |
| `GET /api/system/storage` | Detaillierte Speicher-Aufschlüsselung |

---

## Workflow-Interaktionskarte

```
┌──────────────────────────────────────────────────────────────────────┐
│                        EXTERNE QUELLEN                               │
│  YouTube  ·  Lokale Dateien  ·  Archive  ·  FreeTube  ·  Takeout    │
└───────┬───────────┬──────────────┬──────────────┬────────────┬──────┘
        │           │              │              │            │
        ▼           ▼              ▼              ▼            ▼
   ┌─────────┐ ┌────────┐   ┌──────────┐  ┌──────────┐ ┌──────────┐
   │Download │ │  Scan  │   │  Import  │  │ Archiv   │ │  RSS     │
   │Workflow │ │Workflow│   │ Workflow │  │ Workflow │ │ Polling  │
   └────┬────┘ └───┬────┘   └────┬─────┘  └────┬─────┘ └────┬─────┘
        │          │              │              │            │
        └──────────┴──────┬───────┴──────────────┘            │
                          │                                   │
                          ▼                                   ▼
                   ┌─────────────┐                     ┌───────────┐
                   │   videos    │◄────────────────────│rss_entries│
                   │  (Tabelle)  │     Auto-Download   │ (Tabelle) │
                   └──────┬──────┘                     └───────────┘
                          │
        ┌────────┬────────┼────────┬──────────┬──────────┐
        │        │        │        │          │          │
        ▼        ▼        ▼        ▼          ▼          ▼
   ┌────────┐┌───────┐┌───────┐┌───────┐┌─────────┐┌────────┐
   │Player  ││Kapitel││Lyrics ││Favori-││Kategor- ││Export/ │
   │Stream  ││Ad-Mark││       ││ten    ││ien      ││Backup  │
   └────────┘└───────┘└───────┘└───────┘└─────────┘└────────┘
```

---

## Rate-Limiting

Alle externen API-Aufrufe sind rate-limited (`rate_limiter` Service):

| Ziel | Limiter-Key | Verwendung |
|------|-------------|------------|
| YouTube RSS | `rss` | Feed-Polling, Typ-Klassifikation |
| YouTube pytubefix | `pytubefix` | Suche, Kanal-/Playlist-Traversal, Kapitel |
| Avatar-Download | `avatar` | Kanal-Avatare herunterladen |
| SponsorBlock API | (inline) | Ad-Marker-Import |
| LRCLIB | (inline) | Lyrics-Suche |
| LM Studio | (inline) | Thumbnail-AI-Analyse |
