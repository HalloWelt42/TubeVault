# TubeVault – Bug- & Verbesserungs-Backlog

Stand: 2026-04-19. Neue Einträge unten anhängen. Format pro Eintrag:

```
### [Status] Kurztitel
- **Bereich:** backend|frontend|queue|scanner|…
- **Symptom:** was sieht man
- **Vermutete Ursache:** was ist der Kern
- **Prio:** 🔴 hoch / 🟠 mittel / 🟡 niedrig
```

Status: `[open]` · `[partial]` · `[done]` · `[deferred]` · `[wont-fix]`

---

## Release-Log (was hat welcher Commit geflickt?)

| Version | Kern-Fixes |
|---------|-----------|
| **v2.0.0** | yt-dlp-Migration, Job-Tracking-Refactor, BotDetection & Cipher behoben, Phasenleiste, WS-Sync nach Done, Adapter für Channel.videos (RSS-404-Ersatz) |
| **v2.0.1** | Phase-Rendering bei fertigen Jobs korrekt (buildPhases) |
| **v2.0.2** | Pre-Commit-Hooks gegen verbotene Begriffe |
| **v2.0.3** | Deutsch-Audit (P100 → Prio, Stale fixen → Festhänger befreien, Reset → Zurücksetzen) |
| **v2.0.4** | ETA + Download-Rate im Progress-Label |
| **v2.0.5** | ActivityPanel X-Button keine absolute Überlappung mehr |
| **v2.0.6** | Lyrics-Sidebar öffnet nicht mehr automatisch wenn andere Sidebar aktiv |
| **v2.0.7** | Tab-Leiste Video-Detail: sauberes flex-wrap |
| **v2.0.8** | Subtitle-Download Rate-Limit (caption-Kategorie) + schlanker Log |
| **v2.1.0** | 144p/240p Qualitäten + Datei-Pfad-Kopieren im Meta-Panel |
| **v2.1.1** | Dashboard-Download-Feld mit Qualitäts + Audio-Toggle |
| **v2.1.2** | Prio-Badge nowrap (war zu „Pri"+„5" gebrochen) |
| **v2.1.3** | Downloads-Seite Queue-Item-Actions nicht mehr absolut |
| **v2.1.4** | FE_VERSION aus package.json via Vite define |
| **v2.1.5** | Channel-Poll mit /videos→/shorts→/streams-Fallback, Endlos-Retry-Loop bei non-404-Fehlern gestoppt |
| **v2.1.6** | YT-Suche `/full` Shorts-Erkennung + pytubefix-Singular-Aliase |
| **v2.1.7** | Listen-Reaktivität: VideoCard ruft onUpdate → Parents laden neu. Feed-Tab „Archiv" → „Weggelegt" |
| **v2.1.8** | category_id beim Auto-Download übernommen, Qualitäts-Picker nicht mehr 4K statt 1080p, auto-archive auch ohne drip_enabled |
| **v2.1.9** | Medaillen-Regel: prozentual (≥90 % Silber, ≥70 % Bronze; Groß-Kanal-Gold bei ≤1 fehlend) |
| **v2.1.10** | Zentrale VIDEO_QUALITIES (inkl. 4K/2K), Tag-Liste „+64499 mehr" → Hinweis auf Suchfeld |

---

## Offene Features / Wünsche

### [open] Settings-Seite: jeden Eintrag auditieren (greift er, sinnvoll?)
- **Bereich:** backend + frontend (Einstellungen)
- **Wunsch:** User-Zitat: "in den einstellungen muss jeder einzele punkt geprüft werden ob der greift, überhaupt sinnvoll ist und so."
- **Plan:** Matrix-Audit aller settings-Keys: für jeden Eintrag prüfen
    - Wird er im Backend gelesen?
    - Beeinflusst er tatsächlich Verhalten?
    - Ist die Default-Wahl sinnvoll?
    - Ist das Label verständlich (deutsch)?
    - Fehlen wichtige Einstellungen, die es nicht gibt?
  Offensichtlich tote Einstellungen → entfernen oder markieren. Fehlende wichtige → ergänzen.
- **Prio:** 🟠 mittel (nach dem größten Bug-Brandlöschen)

### [open] Video-Ignore-Liste: gelöschte/unverfügbare Videos nicht erneut auto-laden
- **Bereich:** backend (_auto_queue_video, DELETE-Endpoint) + frontend (ChannelDetail)
- **Symptom/Wunsch:** Videos die geparkt sind (nicht verfügbar) oder vom User gelöscht wurden, werden aktuell beim nächsten Abo-Zyklus wieder in die Queue gestellt. User-Zitat: "kanäle, die video haben die nie geladen werden können oder die wir explizit gelöscht haben dürfen beim abo nicht erneut dieses markierte video laden."
- **Aktuelle Lücke:**
  - `_auto_queue_video` prüft nur `status='error'`, nicht `'parked'` → geparkte kommen zurück in Queue
  - Wenn User Video DELETE'd (aus `videos`-Tabelle), aber Eintrag in `rss_entries` bleibt, wird es wieder gezogen
- **Fix-Plan:**
  1. DB: `rss_entries` bekommt `download_blocked BOOLEAN DEFAULT 0` (oder neuer Wert in feed_status `'blocked'`)
  2. `_auto_queue_video` prüft zusätzlich: `rss_entries.download_blocked=1` → skip; auch jobs mit status `'parked'` (nicht nur 'error') → skip
  3. DELETE-Endpoint `/api/videos/{id}` erhält Option `block_redownload=true` (setzt rss_entries.download_blocked=1)
  4. Frontend: Beim Löschen Dialog „Nur aus Sammlung / Endgültig ignorieren"
  5. **ChannelDetail:** Neue Sektion unter der Video-Liste: „🚫 N Videos werden nicht geladen" mit Liste (Grund: unavailable, parked, manuell ignoriert) + Button „Sperre aufheben"
- **Wird durch v2.0.0-Problem-Videos-Panel teilweise abgedeckt** (parked jobs sind schon sichtbar), aber die „manuell gelöscht"-Logik fehlt komplett.
- **Prio:** 🟠 mittel (vermeidet frustrierende Wiederholungen)

### [open] Batch-Upgrade: Videos unter 1080p global + pro Kanal aufbessern
- **Bereich:** backend (neue Endpoints) + frontend (Settings-Aufräumjob + Kanal-Detail)
- **Ziel:** Videos in der Sammlung, die < 1080p haben, sollen per Batch neu heruntergeladen werden. Ein-Klick-Aktion an zwei Stellen (A + B).
- **Backend-Plan:**
  - `GET  /api/videos/upgrade-candidates?min_quality=1080p&channel_id=UC...`
  - `POST /api/videos/upgrade-batch?min_quality=1080p&channel_id=UC...&priority=-1`
  - Filter: streams.quality-Höhe < min_quality UND source='youtube' UND status='ready'
  - Niedrige Prio (−1) damit normale Downloads Vorrang haben
- **Frontend-Platzierung (beide):**
  - **A** (global): Einstellungen → Aufräum-Jobs → "Qualität aufbessern" mit Dropdown für min_quality
  - **B** (pro Kanal): Kanal-Detail-Seite → Banner "⚠ N Videos unter 1080p — [Aufbessern]"
- **Mindest-Qualität einstellbar:** default 1080p, User kann 720p/1440p/2160p wählen.
- **User-Zitat:** "ich strebe 1080p als minimum an, wenn der kanal das hat und wenn das aktuelle video in der sammlung zu niedrige auflösung hat."
- **Prio:** 🟠 mittel (sinnvoller Aufräum-Job für Altbestand)

### [open] Verwaister Code / Dead-Code-Audit
- **Bereich:** backend + frontend
- **User-Zitat:** "allg müssen wir auch mal sehen was alles verbessert werden kann auch verwaister code."
- **Plan:**
  - Backend: ungenutzte Funktionen, nicht mehr erreichte Endpoints (z.B. pytubefix-Reste die nach yt-dlp-Migration nur noch Fallback sind), doppelte Logik zwischen services
  - Frontend: nicht mehr importierte Komponenten, nicht mehr referenzierte CSS-Klassen, stale $state-Variablen, doppelte Funktionen (z.B. gleiche Logik in Library + Archives)
  - Tools: `grep`-basierter Inventur-Scan, oder eslint + dead-code-detection
- **Approach:** einen dedizierten Audit-Lauf, findings in einer Liste sammeln, dann schrittweise aufräumen (nie alles auf einmal löschen).
- **Prio:** 🟡 niedrig (Qualität, kein Bug) — aber gut für Architektur-Gesundheit

### [open] Adaptives Poll-Intervall pro Kanal aus Upload-Muster
- **Bereich:** backend (rss_service + Scheduler)
- **Problem der jetzigen Logik:** `check_interval` wird bei Miss verdoppelt (max 7 Tage). Nachts uploadet niemand → Interval explodiert unnötig. Creator mit "jeden Montag 18:00"-Schema werden bei perfekter Vorhersage überoptimiert (Check läuft zu selten). Zufallsuploader werden zu oft/selten gepollt.
- **User-Idee:** Upload-Muster **aus den Metadaten bestehender Videos** lernen und daraus den nächsten sinnvollen Check-Zeitpunkt berechnen.
- **Plan:**
  1. **Datenmodell** (in `subscriptions` oder separate Tabelle `channel_upload_profile`):
     - `avg_interval_seconds` – mittlerer Abstand zwischen Uploads
     - `dow_histogram` – Wochentags-Verteilung (7 Werte, 0=So..6=Sa)
     - `hour_histogram` – Tageszeit-Verteilung (24 Werte UTC oder lokal)
     - `variance` / `entropy` – erkennt Muster vs. Zufall
     - `last_upload_at`, `upload_count_analyzed`, `profile_updated_at`
  2. **Analyse-Job** (einmalig + periodisch): Aus `rss_entries.published` pro Kanal die Histogramme + Intervalle berechnen. Läuft auch **rückwirkend** auf Alt-Bestand (User-Idee).
  3. **Scheduler-Logik ersetzt das simple Verdoppeln:**
     - Wenn Muster klar (hohe Konzentration in wenigen DoW/Stunden): nächsten Check auf nächstes "wahrscheinliches Fenster" legen (z.B. Montag 17:30 für "Montag 18:00"-Kanal)
     - Wenn reine Zufallsverteilung (hohe Entropie): Poisson-Modell mit avg_interval — dann Intervall um avg_interval/2 anlegen, bei Miss mild verlängern
     - Nachts (gegen globale Upload-Verteilung außerhalb Kernzeit): immer deprioritisieren
  4. **Fallback:** Wenn kein Profil (neuer Kanal, <5 Videos), alte Logik (Standard-Interval + Verdoppeln).
- **Prio:** 🟠 mittel (klarer Gewinn, aber braucht sauberes Design + Tests)

### [open] Mehrfachauswahl überall + Drag-to-Select mit Maus-Rechteck
- **Bereich:** frontend (Library, Archives, Favorites, History, OwnVideos, ChannelDetail, Playlists)
- **Wunsch:** User-Zitat: "mehrfachauswahl sollte überall verfügbar sein und es sollte auch markiert werden durch drüberziehen mit der maus, wie ein rechteck ziehen."
- **Anforderungen:**
  - Select-Mode auf allen Karten-Listen konsistent verfügbar (aktuell: Library ✓, Archives ✓, andere?)
  - Drag-to-Select: Mausdrücken auf Leerfläche → Rechteck aufziehen → alle Karten innerhalb werden selektiert (wie Finder / Windows-Explorer)
  - Shift-Klick = Range-Selection, Ctrl/Cmd-Klick = Toggle (üblich)
- **Prio:** 🟠 mittel (Workflow-Verbesserung für Batch-Aktionen)

### [open] Eigene YouTube-Suchergebnis-Seite (eigenes Menü, umfassend)
- **Bereich:** frontend (neue Route + Sidebar-Eintrag)
- **Wunsch:** User-Zitat: "die ergebnisse der suchen sollte 1. eine separate suchseite öffnen 2. die ergebnisse sollte umfassender sein kanalinfos, größere thumnails pagineirung über die gesamte seite alles als eigene menü eigene seite, alles grund umfassend"
- **Anforderungen:**
  - Neue Route, z.B. `/youtube-suche?q=...&page=N`
  - Große Thumbnails im Grid
  - Kanal-Infos pro Video (Avatar klickbar, Name klickbar)
  - Echte Pagination-Controls (Prev / Seiten / Next)
  - Separate Bereiche für Shorts/Playlists/Channels
  - Vom SearchDropdown aus erreichbar ("Alle Treffer")
- **Prio:** 🟠 mittel (Feature — gute UX für ausführliche Suche)

### [open] Tag-Filter zeigt globale Tags statt nur der angezeigten Liste
- **Bereich:** frontend + backend (Library, Archives)
- **Symptom:** Bibliothek filtert auf 20 Videos, Tag-Filter zeigt aber 64514 Tags. User-Zitat: "20 videos aber tausenden tags, das kann nie sein."
- **Ursache:** Tags werden global aus `videos.tags` aggregiert, nicht nur aus den aktuell angezeigten/gefilterten Videos.
- **Fix:** Tag-Liste basiert auf den gerade angezeigten Videos (nach Filter-Anwendung). Bei unveränderten Filtern muss Tag-Liste neu berechnet werden.
- **Prio:** 🟠 mittel

### [open] Feed-Bereich: fehlende Filter / schwache Filter-Optionen
- **Bereich:** frontend (Feed-Seite)
- **Symptom:** User-Zitat: "in feeds dagegen fehlt das filtern völlig und nur wenige option sind da."
- **Fix-Plan:** Feed bekommt gleichwertige Filter wie Library (Typen, Kanäle, Kategorien, Tags), plus Feed-spezifische (Zeitraum, gelesen/ungelesen).
- **Prio:** 🟠 mittel

### [open] Sortier-Optionen erweitern (Upload-Datum + Favoriten)
- **Bereich:** frontend (Library, Archives, ChannelDetail) + backend (falls nicht da)
- **Wunsch:** Neben "Datum/Titel/Dauer/Größe/Bewertung/Abgespielt" auch "Upload-Datum" und "Favoriten" als Sortier-Option.
- **Backend:** `sort_by=upload_date` + `sort_by=is_favorite` im Videos-API.
- **Prio:** 🟠 mittel (schon als Ticket `Sortierung nach YT-Upload-Datum` angelegt, hier präzisiert)

### [open] Video/Shorts-Kategorisierung nachträglich korrigieren (aktiv triggerbar)
- **Bereich:** backend (rss_entries + videos) + frontend (Button in Settings)
- **Geschichte:** früher wurde mit pytubefix + typ-getrennten Feeds kategorisiert — fehleranfällig. Seit yt-dlp-Migration (v2.0.0) nutzen wir `duration ≤ 60` = short, sonst video. Neue Einträge sind sauber.
- **Problem:** Alt-Bestand kann falsche video_type-Werte haben.
- **Feature:** Aktiver "Reklassifizieren"-Durchlauf — iteriert über rss_entries + videos, setzt video_type basierend auf duration neu. Häppchen-mode (nicht alle auf einmal).
- **Prio:** 🟡 niedrig (nice-to-have, nicht datenkritisch)


### [open] Sortierung nach YouTube-Upload-Datum (nicht nur Download-Datum)
- **Bereich:** frontend (Sort-Dropdowns in Library, Feed, ChannelDetail) + backend (API-Sortierung)
- **Wunsch:** Aktuell sortieren Listen nach `download_date` (wann heruntergeladen). Optionally: nach `upload_date` (YouTube-Originaldatum aus Metadaten). Das Feld existiert in `videos.upload_date`.
- **Fix-Plan:**
  1. Backend: `GET /api/videos` akzeptiert `sort_by=upload_date` (prüfen, ob schon da)
  2. Frontend: Sort-Dropdown um "Upload-Datum" erweitern
- **Prio:** 🟠 mittel

### [open] Metadaten schon beim Scanning in Suchindex aufnehmen
- **Bereich:** backend (scanner, search index)
- **Beschreibung:** Beschreibung, Tags, Untertitel bereits beim Kanal-Scan laden und in Suchindex packen — bessere Suche ohne echten Download. In Einstellungen de-/aktivierbar.
- **Zusammenhang:** passt gut zur geplanten "zarte Häppchen"-Scanner-Überarbeitung. Muss aber YouTube-schonend sein (API-Calls pro Video).
- **Prio:** 🟠 mittel

### [done] Datei-Pfad in Metadaten verlinkbar (v2.1.0)
- **Bereich:** frontend (Video-Detail)
- **Beschreibung:** Direkter Link zum Dateipfad auf dem Host — "Im Dateimanager anzeigen".
- **Prio:** 🟡 niedrig (Komfort)

### [done] Dashboard-Download-Feld mit Qualitätsauswahl + Audio-Toggle (v2.1.1)
- **Bereich:** frontend (Dashboard)
- **Beschreibung:** Dashboard hat ein kleineres Download-Widget. Soll dasselbe Feld wie in "Jobs" bekommen — inkl. Auswahl-Menü für Video-Qualität.
- **Prio:** 🟠 mittel (Konsistenz)

### [done] Qualitäten 144p/240p im Download-Menü (v2.1.0)
- **Bereich:** frontend (Quality-Select) + backend (Picker)
- **Beschreibung:** Niedrige Qualitäten für schmalbandige / mobile Szenarien. Aktuell fehlen sie im Dropdown.
- **Prio:** 🟡 niedrig (einfach, aber kein Engpass)

### [open] YouTube-Playlisten abonnieren (oder direkt downloaden)
- **Bereich:** backend (subscriptions/playlists) + frontend
- **Beschreibung:** Analog zu Kanal-Abos: Playlisten abonnieren, neue Videos auto-downloaden. Fallback: nur einmalig runterladen via Playlist-URL.
- **Prio:** 🟠 mittel

### [deferred] Transkript-Service (später, explizit nachgelagert)
- **Zustand:** aktuell keine Priorität (User-Entscheidung).
- **Fixe Vorgaben für später:**
  - **Nur Whisper-Large** (keine kleinen Modelle)
  - **Nativ laufen**, nicht in Docker (eigener systemd-Service)
  - Trigger **nur** wenn keine YouTube-Untertitel vorhanden
  - Trigger **nur** explizit vom User (kein Auto-Batch, kein Auto-on-Download)
  - Ablage `data/transcripts/…`, Pfad-Schema bei Umsetzung festlegen
  - Transkripte in FTS5-Such-Index
- **Umfasst die früheren Tickets:** "Transkript bei Download", "nachträglich erstellen", "separat ablegen", "im Such-Index"

---

## Offene Bugs

### [done] YouTube-Suche `/full`: Shorts/Playlists/Channels leer (v2.1.6, pytubefix-Singular-Aliase + Shorts via Duration-Filter)
- **Bereich:** backend (`ytdlp_adapter.SearchAdapter`)
- **Symptom:** `/api/search/youtube/full?q=...` gibt `videos` korrekt, aber `shorts=[]`, `playlists=[]`, `channels=[]`, `suggestions=[]`. Frontend-Dropdown zeigt leere Tabs.
- **Ursache 1:** Router nutzt pytubefix-Singular-Properties `s.playlist`, `s.channel`, `s.completion_suggestions` — Adapter hat Plural `playlists`/`channels`/`suggestions`. AttributeError wird von try/except geschluckt, bleibt leer.
- **Ursache 2:** Adapter-Properties `playlists`/`channels` returnen hartkodiert `[]`. yt-dlp's `ytsearchN:q` liefert aber gemischte Entry-Typen — man müsste `entry.get('_type')` prüfen und entsprechend aufteilen.
- **Fix-Plan:** SearchAdapter implementiert `playlist`/`channel` Aliase UND parst yt-dlp-Entries korrekt in die vier Kategorien.
- **Prio:** 🔴 hoch (User-Zitat: "wir können aktuell nix mehr bei YT suchen")

### [open] YouTube-Suche: echte Paginierung gewünscht
- **Bereich:** backend (Search-Endpoint) + frontend (Result-Rendering)
- **Symptom/Wunsch:** Aktuell liefert `/api/search/youtube/full` max_results ≤30 in einem Call. User wünscht sich „wie Google", also Paginierung durch **alle** Treffer.
- **Fix-Plan:** yt-dlp `ytsearch{N}:q` mit großem N (z.B. 200) + Server-Side-Pagination in der API (offset/limit). Frontend: Infinite-Scroll oder "Weitere Seiten"-Button.
- **Prio:** 🟠 mittel (Feature, nachdem der leere-Tabs-Bug oben gelöst ist)

### [partial] Tag-Liste zeigt „+64499 mehr" – unsinnig
- **Bereich:** frontend (Tag-Filter) + backend (Tag-Bereinigung)
- **Symptom:** Tag-Panel zeigt die Top-Tags und dahinter „+64499 mehr" — sinnlos bei 64.514 Gesamt-Tags. Max ~60 sinnvoll darstellbar.
- **Ursachen:** 
  1. Datenverschmutzung: 64k Tags sind aggregierte YouTube-Tags aus Millionen Videos, meist unsinnig (Ein-Zeichen-Tags, Pseudo-Tags, Zufalls-Strings).
  2. Frontend zeigt die Total-Zahl statt eine sinnvolle "Weitere anzeigen"-UX (Suchfeld ist da, aber Button irreführend).
- **Fix-Plan:**
  1. **Frontend:** Top ~50 Tags + einfaches Suchfeld, KEINE "+N mehr"-Textanzeige (Zahl weglassen oder als "weitere Tags via Suche filtern").
  2. **Backend-Aufräumjob:** Tags filtern (min. 2 Zeichen, min. Count ≥ X, keine Pseudo-Whitespace, etc.)
- **Prio:** 🟠 mittel (UX-Reibung, keine Datenfehler)

### [open] Aufräum-Jobs in den Einstellungen fehlen
- **Bereich:** backend (Maintenance-Service) + frontend (Settings-Panel)
- **Wunsch:** In den Einstellungen ein „Aufräumen"-Bereich mit Jobs:
  - Unsinnige Tags löschen + aus allen Videos entfernen (z.B. Tags mit <3 Zeichen, Ein-Wort-Zufallsstrings, Count ≤ 1)
  - (Potentiell mehr: Waisen-Metadaten, fehlende Dateien, Doppelte, etc.)
- **Architektur:** Jeder Aufräum-Job als eigener job_type, über job_service laufen (mit Fortschritt). Frontend: Liste der Aufräum-Jobs mit "Jetzt ausführen"-Button + letzter Lauf + Konfig-Parametern.
- **Prio:** 🟠 mittel (nützlich, nicht dringend)

### [done] Kanal-Einstellungen: category_id wird bei Download nicht übernommen (v2.1.8, video_categories-M2M wird nach Download angelegt)
- **Bereich:** backend (`download_service._process`)
- **Symptom:** Wenn ein Abo einer Kategorie zugewiesen ist (`subscriptions.category_id`), wird das heruntergeladene Video NICHT automatisch dieser Kategorie zugeordnet. INSERT INTO videos enthält kein `category_id`.
- **Fix:** In `_process` den `sub.category_id` abfragen (via channel_id → subscriptions) und beim INSERT/UPDATE des Videos setzen. Siehe aber: `videos.category_id` existiert NICHT in der Spalte — separate Tabelle `video_categories`? Ggf. über `video_categories`-Zuordnung.
- **Prio:** 🟠 mittel (wird explizit vom User vermisst)

### [partial] Listen/Cards: Darstellung reaktiv fehlerhaft nach Archiv-Aktion
- **Bereich:** frontend (Library, Archives, Channel-Detail — alle Card-Listen)
- **Symptom:** Nach "Video ins Archiv verschieben" bleiben Karten angezeigt, die dort nicht mehr hingehören. Erst ein Reload aktualisiert die Darstellung. User-Zitat: "fehlen oft welche wenn man einige in den archiv verschiebt und nur reload erneuert die darstellung. die darstellung ist allg mega verbuggt, falsch und inkonsistent"
- **Vermutete Ursache:** Listen-State wird nicht nach Mutation invalidiert. Backend-API erfolgreich → aber lokale `videos`-Array nicht synchronisiert. Fehlendes Event/Store-Update.
- **Fix-Plan:** Nach Mutations-API (archive/unarchive/delete) den betroffenen Eintrag aus der lokalen Liste entfernen + Parent-State zurückschicken (Event oder Store). Optional: Store für Video-Status (archived/ready), der alle Listen-Views automatisch aktualisiert.
- **Prio:** 🔴 hoch (User sagt "mega verbuggt, falsch und inkonsistent")

### [open] Weitere Kanal-Einstellungen-Bugs (User-Report: "funktionieren nicht wie eingestellt")
- **Bereich:** backend (subscriptions + rss_service + download_service)
- **Symptom:** User-Zitat: "viele einstellungen der kanäle [funktionieren] nicht wie eingestellt".
- **Fix-Plan:** Systematischer Audit jeder Einstellung (auto_download, download_quality, audio_only, drip_*, suggest_exclude, category_id, enabled). Pro Feld klar dokumentieren: wo gesetzt, wo abgefragt, Testcase.
- **Status:** Audit begonnen (category_id als erster Befund, siehe Eintrag oben). Weitere folgen.
- **Prio:** 🔴 hoch

### [done] Audio-Only-Download extrem langsam (v2.0.0, yt-dlp intern → 67× schneller)
- **Bereich:** backend (`ytdlp_adapter.StreamAdapter.download`)
- **Symptom:** Audio-Only-Download läuft durch, aber ~32 KB/s statt ~9 MB/s (Test-Wert für Video-Stream). User-Zitat: "steht scheinbar still / extrem träge".
- **Ursache:** Unser Adapter lädt die Stream-URL per `httpx.stream` direkt. YouTube drosselt solche nackten Downloads; `yt-dlp` hat eingebaute Anti-Throttle-Logik (Chunking, Re-Request, Player-Hinting).
- **Fix:** `StreamAdapter.download()` intern auf `yt_dlp.YoutubeDL().download()` umstellen (nur das konkrete Format via `format_id`).
- **Prio:** 🔴 hoch (Kernfunktion stark beeinträchtigt, betrifft auch Video-Adaptive-Downloads, nicht nur Audio)

### [done] Frontend-Anzeige bleibt stehen nach Job-Ende (v2.0.0, handleProgressMessage übernimmt Terminal-Status sofort)
- **Bereich:** frontend (Queue-Komponente) + backend (WS-Broadcast)
- **Symptom:** Backend meldet Job als `done` mit progress=1.0, Frontend zeigt aber weiter alten "aktiv"-Zustand — "Anzeige tot / verbuggt" laut User.
- **Vermutete Ursache:** Final-State WS-Message geht verloren oder wird vom Frontend nicht auf die Queue-Box gemappt. Throttle `WS_THROTTLE=0.4s` könnte den finalen Broadcast schlucken.
- **Prio:** 🔴 hoch (User hat nie die Bestätigung, dass ein Job durch ist)

### [done] Auto-Subtitle-Download HTTP 429 (v2.0.8, eigene rate_limiter-Kategorie 'caption')
- **Bereich:** backend (`download_service.download_subtitles`)
- **Symptom:** Nach dem Audio/Video-Download versucht auto-subtitle alle Config-Sprachen → YouTube antwortet mit 429 Too Many Requests.
- **Vermutete Ursache:** Caption-API hat ein eigenes Rate-Limit, wird aber nicht über den rate_limiter gesteuert. Mehrere Sprachen parallel / zu schnell nach Download.
- **Fix:** Caption-Calls sollten eine eigene rate_limiter-Kategorie bekommen (z.B. `caption`, Intervall 3-5s), Retry mit Backoff bei 429.
- **Prio:** 🟠 mittel

### [done] Subtitle-Log spammt alle 150+ Caption-Sprachen (v2.0.8, schlanker Log)
- **Bereich:** backend (`download_service.download_subtitles` Log)
- **Symptom:** `[SUBS] VID: Verfügbare Captions: a.ab (Abkhazian), a.aa (Afar), ...` — ca. 4000 Zeichen Log pro Video. Macht den Live-Log unlesbar.
- **Fix:** Nur matching/gewünschte Sprachen loggen, oder Anzahl + erste 5 als Debug.
- **Prio:** 🟡 niedrig (kosmetisch, aber nervig)

### [done] Phasenleiste: eine Komponente, verschiedene Zustände
- **Gelöst in v2.0.1:** `ActivityPanel.buildPhases()` wählt die richtige Phasen-Liste aus (PHASES_AUDIO/PROGRESSIVE/ADAPTIVE) basierend auf `job.metadata.download_options`. `DownloadProgress` rendert stur, was reinkommt. Backend ist Wahrheit (sendet `phases` im WS), Frontend hat Fallback-Templates für den Fall, dass Backend-phases fehlen.
- **Trade-off:** Phasen-Templates existieren redundant in Backend + Frontend. Akzeptiert für Einfachheit.

### [done] Englisches Prio-Label "P100" (v2.0.3 → "Prio X"; v2.1.2 nowrap-Fix)
- **Bereich:** frontend (Queue-Box Badge)
- **Symptom:** Priorität 100 wird als "P100" (englische Kurzform) gerendert.
- **Fix:** "Prio 100" oder "Priorität 100" (deutsch). Siehe auch Sprach-Audit-Ticket.
- **Prio:** 🟡 niedrig

### [done] Tab-Bereich im Video-Detail Zeilenumbruch (v2.0.7, flex-wrap + row-gap)
- **Bereich:** frontend (Video-Detail-Tabs)
- **Symptom:** Tab-Leiste "Info · Kapitel · Werbung · Untertitel · Streams" bricht optisch unschön um bzw. rendert einen Zeilenumbruch da, wo keiner erwartet wird. (Screenshot Sting-Video.)
- **Vermutete Ursache:** flex/wrap-Layout der Tab-Bar ohne min-width oder ohne Overflow-Handling.
- **Prio:** 🟡 niedrig (kosmetisch, aber stört regelmäßig)

### [open] Buttons und Badges visuell kaum unterscheidbar
- **Bereich:** frontend (Design-System / CSS)
- **Symptom:** User-Zitat: "funktionale buttons und badges sind kaum zu trennen im UI". Buttons sehen wie Badges aus, Badges wie Buttons — unklar, was klickbar ist.
- **Fix-Richtung:** Klare Design-Tokens: Buttons bekommen Hover/Active-States, Shadow, Border-Style; Badges bleiben flache Labels ohne Hover-Interaktion. CSS-Audit der Badge-/Button-Komponenten, Duplikate konsolidieren.
- **Prio:** 🟠 mittel (UX-Reibung)

### [done] Queue-Box X-Button überdeckt Bedienelemente (v2.0.5 ActivityPanel + v2.1.3 Downloads)
- **Bereich:** frontend (Queue-Box / Action-Buttons)
- **Symptom:** Der X-Button (Abbrechen) in der rechten Action-Spalte überlappt mit darunter/dahinter liegenden Elementen (Badge, Medaille, Status-Icon). Sichtbar im Fertig-Panel.
- **Vermutete Ursache:** absolute Positionierung ohne z-index-Hierarchie, oder fehlendes padding/margin im Button-Container.
- **Fix:** z-index-Layer-Vergabe, ggf. Flex-Container statt absolutem Stacking.
- **Prio:** 🟠 mittel (macht Bedienung unzuverlässig)

### [open] Layout-Überdeckungen/Überschneidungen systemisch in der gesamten App
- **Bereich:** frontend (Layout / CSS / Komponenten-Stacking)
- **Symptom:** Elemente überdecken sich gegenseitig, Texte und Inhalte sind teils nicht lesbar. Zieht sich durch alle Bereiche.
- **Vermutete Ursache:** fehlende z-index-Disziplin, nicht responsive Container, absolute Positionierung ohne Constraints, fehlende overflow-Handling, zu viele overlay-Panels gleichzeitig.
- **Fix-Richtung:** Systematische Frontend-Audit — CSS-Layer definieren (Modal > Toast > Dropdown > Panel > Content), responsive Container mit min-widths, ein globales Layout-Grid das Panels koordiniert.
- **Prio:** 🟠 mittel (User-sichtbar, aber kein Datenverlust)

### [done] Layout Lyrics+Feed parallel automatisch (v2.0.6, auto-open nur wenn keine andere Sidebar)
- **Bereich:** frontend (Layout, Panel-Manager)
- **Symptom:** Video-Start aus Bibliothek öffnet automatisch Lyrics **und** Feed — Haupt-Viewport wird auf ~110px komprimiert, Titel bricht hart um ("Sting -  Shape of  My Heart  (Live at the Rijksmuseur" jedes Wort eigene Zeile).
- **Wunsch:** Vorherige Panel-Sichtbarkeit beibehalten, nicht automatisch einblenden. Bei zu wenig Platz: Panels nicht parallel öffnen, sondern nur eines (oder sie müssen sich overlaying verhalten).
- **Prio:** 🟠 mittel (nicht daten­kritisch, aber sehr störend)


### [open] Tech-Englisch statt Deutsch in UI / API / Buttons
- **Bereich:** frontend + backend (user-sichtbare Strings)
- **Symptom:** Begriffe wie `fix-stale`, Status-Labels, Button-Beschriftungen teils englisch — User versteht nicht, was gemeint ist.
- **Beispiele:** "fix-stale" → "Festhänger befreien" / "Aufräumen". "purge" → "leeren". "retry" → "erneut versuchen".
- **Lösung:** Inventur der user-sichtbaren Strings (frontend/*.svelte, routers/*.py Error-Messages, Button-Labels), durchgängig deutsch.
- **Prio:** 🟠 mittel (macht UX unnötig schwer, aber keine Datenfehler)


### [open] Queue-Box ohne Titel wenn Metadaten noch nicht geladen
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Boxen zeigen nur die Video-ID (z.B. `i9GY4n9aIkA`) ohne Titel, ohne Progress, ohne Phasenleiste.
- **Vermutete Ursache:** Fallback-Rendering fehlt. Titel wird erst nach Resolve befüllt, UI hat kein Placeholder.
- **Prio:** 🟠 mittel

### [open] Queue-Box zeigt Phasenleiste bei `is unavailable`-Fehler
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Rotes Error-Icon + 2% Progress + vollständige Phasenleiste (Auflösen · Video · Audio · Merge · Abschluss) — suggeriert, dass der Download noch weiterläuft.
- **Vermutete Ursache:** Error-State unterdrückt die normale Progress-Darstellung nicht.
- **Prio:** 🟠 mittel

### [done] Phasenleiste inkonsistent progressive/adaptive (v2.0.1, buildPhases() in ActivityPanel)
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Box 1 zeigt 3 Phasen (Auflösen · Video · Abschluss), Box 2 zeigt 5 (+ Audio + Merge). Optisch verwirrend.
- **Vermutete Ursache:** Phasen werden dynamisch erzeugt, aber die Darstellung signalisiert nicht, warum die eine Box weniger Phasen hat.
- **Prio:** 🟡 niedrig (technisch korrekt, aber UX-Reibung)

### [done] UI zeigt falsche Phase bei Audio-Only (v2.0.3 Backend + v2.0.1 Frontend)
- **Bereich:** frontend (DownloadQueue) + backend (`_on_progress`)
- **Symptom:** Audio-Download läuft bereits, Queue-Box behauptet weiter "Video wird heruntergeladen".
- **Vermutete Ursache:** Phase-Umschaltung zwischen Video- und Audio-Download wird nicht zuverlässig via WS gebroadcastet — vermutlich Race oder WS_THROTTLE verschluckt die Phasen-Änderung.
- **Prio:** 🔴 hoch (irreführt beim Überwachen von Downloads)

### [done] ETA / Restzeit-Schätzung im Progress-Label (v2.0.4)
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Es gibt nur `bytes_done/bytes_total` und Prozent — keine Schätzung der verbleibenden Zeit basierend auf bisherigem Durchsatz.
- **Vermutete Ursache:** ETA wird nicht berechnet/gebroadcastet.
- **Prio:** 🟠 mittel

### [done] RSS-Feed von YouTube 404 (v2.0.0, durch yt-dlp Channel.videos ersetzt; v2.1.5 Shorts/Streams-Fallback)
- **Bereich:** backend (`rss_service`)
- **Symptom:** `https://www.youtube.com/feeds/videos.xml?channel_id=...` liefert HTTP 404, selbst für Rick Astley & Google Developers, auch mit Browser-UA.
- **Vermutete Ursache:** YouTube hat den RSS-Endpunkt blockiert (serverseitig oder IP-gatet).
- **Lösung:** Channel-Updates über yt-dlp `Channel.videos` statt RSS, mit Throttle-Logik wie Scanner-Häppchen.
- **Prio:** 🔴 hoch

### [open] Channel-Scanner zu aggressiv (Massen-Batches)
- **Bereich:** backend (`channel_scanner`)
- **Symptom:** Scannt komplette Kanäle in einem Rutsch (z.B. 400 Videos), wird von YouTube als Bot-Traffic gewertet.
- **Lösung:** Zarte Häppchen — z.B. 10-20 Videos/Tick, Pausen, über 24h verteilt. Scheduler-Logik > Scan-Speed.
- **Prio:** 🔴 hoch

### [done] Unerreichbare Videos Endlos-Retry (v2.0.0 park-Logik; v2.1.5 last_checked-Fix)
- **Bereich:** backend (download queue)
- **Symptom:** Videos mit dauerhaften Fehlern (deleted, private, members-only, region-blocked) retryen weiter bis max_retries.
- **Lösung:** Fehlerarten klassifizieren, dauerhafte Fehler → Status setzen (`unavailable`, `private`, `members_only`, `region_blocked`). Skip-Logik + Editierbarkeit im Frontend pro Kanal.
- **Prio:** 🔴 hoch

### [done] Job-Tracking unsauber (v2.0.0 Refactor: zentraler Status-Writer, Safety-Net, Doppel-start entfernt)
- **Bereich:** backend (download_service, job_service, WS-Broadcaster, evtl. weitere)
- **Symptom:** 
  - 183 Zombie-"active"-Jobs nach BotDetection-Nacht (Exception-Path setzt Status nicht zurück).
  - User-Zitat: "tracken der aktiven downloads funktioniert nie sauber, oft Probleme mit parallelen Jobs obwohl alles nur per einer Queue gesteuert werden sollte. Verdacht: mehrfache Implementierung, Sachen überschneiden sich."
- **Vermutete Ursachen (müssen audited werden):**
  1. Exception-Handling in `_process` setzt Status nicht zuverlässig auf error/retry_wait.
  2. Mögliche Doppel-Worker — z.B. job_service + download_service schreiben beide auf `jobs.status`.
  3. WebSocket-Broadcaster senden widersprüchliche Updates.
  4. Queue-Semaphore greift nicht bei allen Einstiegspunkten (Retry/Resume/Batch).
- **Fix-Plan:**
  1. Inventur: Wer schreibt `jobs.status`? (grep UPDATE jobs SET status)
  2. Inventur: Wie viele WS-Broadcaster gibt's? (grep _ws_broadcast / websocket)
  3. Zentraler Status-Writer — nur eine Stelle soll Status transitions verantworten.
  4. Exception-Handling: immer Status auf error/retry_wait bei Fehler (try/finally).
- **Prio:** 🔴 hoch (systemisches Problem, Auslöser vieler UI-Folgebugs)

### [done] 156 Alt-Jobs in der Queue aus pytubefix-Ära (User hat retry-all manuell ausgeführt)
- **Bereich:** queue
- **Symptom:** Viele gequeuete Downloads aus der Zeit vor dem yt-dlp-Umstieg, teilweise mit BotDetection-Retries.
- **Lösung:** Nach yt-dlp-Validierung einmal `retry-all` + anschließende Analyse welche *echt* unavailable sind.
- **Prio:** 🟡 niedrig (sortiert sich nach den anderen Fixes)

### [open] Docker-Deployment durch direkten systemd-Betrieb ablösen (optional)
- **Bereich:** Deployment (Pi 5)
- **Idee:** Backend als Python `.venv` + systemd-Unit, Frontend-Build als statische Files via nginx-Host-Service.
- **Vorteile:** ~150-200 MB weniger RAM, direkter Pfad-Zugriff ohne Volumes, einfachere Logs via journalctl, schnellerer Start.
- **Voraussetzung:** vorher Block 5 (hardcoded Pfade als Env-basiert) — sonst wird Migration fragil.
- **Aufwand:** ca. 2-3h. Keine Backend-Code-Änderung, nur Deployment-Struktur.
- **Prio:** 🟡 niedrig (Komfort/Optimierung, keine Funktionsverbesserung)

### [open] Hardcodierte IP-Adressen in der App
- **Bereich:** frontend / config (genauer Ort noch zu inventarisieren)
- **Symptom:** IPs wie `192.168.178.49` im Code statt aus einer Config-/Env-Variable.
- **Risiko:** bei Netzwechsel / neuer Hardware müssen mehrere Dateien angefasst werden.
- **Fix-Richtung:** Inventur (grep nach `192.168.` und `localhost:80*`), dann zentrale Config (`VITE_API_URL`, Nginx-Proxy-Variable, Backend-`PUBLIC_URL`).
- **Prio:** 🟡 niedrig (läuft aktuell, Umbau ist Fleißarbeit)

### [open] Hardcodierte Datei-Pfade in Code & DB
- **Bereich:** backend (config, DB-Einträge in `videos.file_path` etc.)
- **Symptom:** Absolute Pfade wie `/mnt/tb26/tubevault/videos/…` oder `/app/data/videos/…` sowohl im Code als auch in DB-Zeilen. Bei Umzug oder Pfad-Umstrukturierung reißen Medien-Links.
- **Risiko:** HOCH — wenn unsauber migriert, verlieren wir die Verbindung zwischen DB und Dateien. User-Zitat: "da kann viel kaputt gehen".
- **Fix-Richtung (später):** Pfade in DB als *relativ* zum Mediendatengrundordner speichern, Basis-Pfad aus Env kommt bei Laufzeit dazu. Migrations-Script mit trockenem Lauf + Backup.
- **Prio:** 🟡 niedrig (bewusst nicht jetzt — nur listen, damit's nicht vergessen wird)

### [open] Andere UI-Kaputtheiten – Doppel-Implementierungen vermutet
- **Bereich:** frontend (unspezifisch)
- **Symptom:** User-Zitat: "irgendwann sind die UIs kaputt gewesen, entweder doppelt implementiert oder andere Fehler".
- **Vermutete Ursache:** Wachstums-Spuren, mehrere Komponenten für die gleiche Sache.
- **Lösung:** Inventur der Frontend-Komponenten, Duplikate konsolidieren.
- **Prio:** 🟠 mittel (erst konkrete Bugs sammeln, dann Aufräumrunde)

---

## Erledigt

### [done] pytubefix BotDetection bei allen Downloads
- **Gelöst:** Umstieg auf yt-dlp via Adapter (Commit folgt).

### [done] pytubefix Cipher RegexMatchError
- **Gelöst:** durch yt-dlp-Umstieg obsolet.
