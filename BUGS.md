# TubeVault – Bug- & Verbesserungs-Backlog

Stand: 2026-04-19. Neue Einträge unten anhängen. Format pro Eintrag:

```
### [Status] Kurztitel
- **Bereich:** backend|frontend|queue|scanner|…
- **Symptom:** was sieht man
- **Vermutete Ursache:** was ist der Kern
- **Prio:** 🔴 hoch / 🟠 mittel / 🟡 niedrig
```

Status: `[open]` · `[in-progress]` · `[done]` · `[wont-fix]`

---

## Offene Features / Wünsche

### [open] Video/Shorts-Kategorisierung nachträglich korrigieren (aktiv triggerbar)
- **Bereich:** backend (rss_entries + videos) + frontend (Button in Settings)
- **Geschichte:** früher wurde mit pytubefix + typ-getrennten Feeds kategorisiert — fehleranfällig. Seit yt-dlp-Migration (v2.0.0) nutzen wir `duration ≤ 60` = short, sonst video. Neue Einträge sind sauber.
- **Problem:** Alt-Bestand kann falsche video_type-Werte haben.
- **Feature:** Aktiver "Reklassifizieren"-Durchlauf — iteriert über rss_entries + videos, setzt video_type basierend auf duration neu. Häppchen-mode (nicht alle auf einmal).
- **Prio:** 🟡 niedrig (nice-to-have, nicht datenkritisch)


### [open] Metadaten schon beim Scanning in Suchindex aufnehmen
- **Bereich:** backend (scanner, search index)
- **Beschreibung:** Beschreibung, Tags, Untertitel bereits beim Kanal-Scan laden und in Suchindex packen — bessere Suche ohne echten Download. In Einstellungen de-/aktivierbar.
- **Zusammenhang:** passt gut zur geplanten "zarte Häppchen"-Scanner-Überarbeitung. Muss aber YouTube-schonend sein (API-Calls pro Video).
- **Prio:** 🟠 mittel

### [open] Datei-Pfad in Metadaten verlinkbar ("Im Finder anzeigen")
- **Bereich:** frontend (Video-Detail)
- **Beschreibung:** Direkter Link zum Dateipfad auf dem Host — "Im Dateimanager anzeigen".
- **Prio:** 🟡 niedrig (Komfort)

### [open] Dashboard: gleiches Download-Feld wie bei Jobs (inkl. Qualitätsauswahl)
- **Bereich:** frontend (Dashboard)
- **Beschreibung:** Dashboard hat ein kleineres Download-Widget. Soll dasselbe Feld wie in "Jobs" bekommen — inkl. Auswahl-Menü für Video-Qualität.
- **Prio:** 🟠 mittel (Konsistenz)

### [open] Qualitäten 144p/240p im Download-Menü ergänzen
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

### [open] Audio-Only-Download extrem langsam (YouTube-Throttling)
- **Bereich:** backend (`ytdlp_adapter.StreamAdapter.download`)
- **Symptom:** Audio-Only-Download läuft durch, aber ~32 KB/s statt ~9 MB/s (Test-Wert für Video-Stream). User-Zitat: "steht scheinbar still / extrem träge".
- **Ursache:** Unser Adapter lädt die Stream-URL per `httpx.stream` direkt. YouTube drosselt solche nackten Downloads; `yt-dlp` hat eingebaute Anti-Throttle-Logik (Chunking, Re-Request, Player-Hinting).
- **Fix:** `StreamAdapter.download()` intern auf `yt_dlp.YoutubeDL().download()` umstellen (nur das konkrete Format via `format_id`).
- **Prio:** 🔴 hoch (Kernfunktion stark beeinträchtigt, betrifft auch Video-Adaptive-Downloads, nicht nur Audio)

### [open] Frontend-Anzeige bleibt stehen nach Job-Ende (WS-Sync)
- **Bereich:** frontend (Queue-Komponente) + backend (WS-Broadcast)
- **Symptom:** Backend meldet Job als `done` mit progress=1.0, Frontend zeigt aber weiter alten "aktiv"-Zustand — "Anzeige tot / verbuggt" laut User.
- **Vermutete Ursache:** Final-State WS-Message geht verloren oder wird vom Frontend nicht auf die Queue-Box gemappt. Throttle `WS_THROTTLE=0.4s` könnte den finalen Broadcast schlucken.
- **Prio:** 🔴 hoch (User hat nie die Bestätigung, dass ein Job durch ist)

### [open] Auto-Subtitle-Download schlägt mit HTTP 429 fehl
- **Bereich:** backend (`download_service.download_subtitles`)
- **Symptom:** Nach dem Audio/Video-Download versucht auto-subtitle alle Config-Sprachen → YouTube antwortet mit 429 Too Many Requests.
- **Vermutete Ursache:** Caption-API hat ein eigenes Rate-Limit, wird aber nicht über den rate_limiter gesteuert. Mehrere Sprachen parallel / zu schnell nach Download.
- **Fix:** Caption-Calls sollten eine eigene rate_limiter-Kategorie bekommen (z.B. `caption`, Intervall 3-5s), Retry mit Backoff bei 429.
- **Prio:** 🟠 mittel

### [open] Subtitle-Log spammt alle 150+ Caption-Sprachen in einer Zeile
- **Bereich:** backend (`download_service.download_subtitles` Log)
- **Symptom:** `[SUBS] VID: Verfügbare Captions: a.ab (Abkhazian), a.aa (Afar), ...` — ca. 4000 Zeichen Log pro Video. Macht den Live-Log unlesbar.
- **Fix:** Nur matching/gewünschte Sprachen loggen, oder Anzahl + erste 5 als Debug.
- **Prio:** 🟡 niedrig (kosmetisch, aber nervig)

### [done] Phasenleiste: eine Komponente, verschiedene Zustände
- **Gelöst in v2.0.1:** `ActivityPanel.buildPhases()` wählt die richtige Phasen-Liste aus (PHASES_AUDIO/PROGRESSIVE/ADAPTIVE) basierend auf `job.metadata.download_options`. `DownloadProgress` rendert stur, was reinkommt. Backend ist Wahrheit (sendet `phases` im WS), Frontend hat Fallback-Templates für den Fall, dass Backend-phases fehlen.
- **Trade-off:** Phasen-Templates existieren redundant in Backend + Frontend. Akzeptiert für Einfachheit.

### [open] Englisches Prio-Label "P100" in Queue-Box
- **Bereich:** frontend (Queue-Box Badge)
- **Symptom:** Priorität 100 wird als "P100" (englische Kurzform) gerendert.
- **Fix:** "Prio 100" oder "Priorität 100" (deutsch). Siehe auch Sprach-Audit-Ticket.
- **Prio:** 🟡 niedrig

### [open] Tab-Bereich im Video-Detail mit unerwünschtem Zeilenumbruch
- **Bereich:** frontend (Video-Detail-Tabs)
- **Symptom:** Tab-Leiste "Info · Kapitel · Werbung · Untertitel · Streams" bricht optisch unschön um bzw. rendert einen Zeilenumbruch da, wo keiner erwartet wird. (Screenshot Sting-Video.)
- **Vermutete Ursache:** flex/wrap-Layout der Tab-Bar ohne min-width oder ohne Overflow-Handling.
- **Prio:** 🟡 niedrig (kosmetisch, aber stört regelmäßig)

### [open] Buttons und Badges visuell kaum unterscheidbar
- **Bereich:** frontend (Design-System / CSS)
- **Symptom:** User-Zitat: "funktionale buttons und badges sind kaum zu trennen im UI". Buttons sehen wie Badges aus, Badges wie Buttons — unklar, was klickbar ist.
- **Fix-Richtung:** Klare Design-Tokens: Buttons bekommen Hover/Active-States, Shadow, Border-Style; Badges bleiben flache Labels ohne Hover-Interaktion. CSS-Audit der Badge-/Button-Komponenten, Duplikate konsolidieren.
- **Prio:** 🟠 mittel (UX-Reibung)

### [open] Queue-Box X-Button überdeckt andere Bedienelemente
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

### [open] Layout bricht zusammen, wenn beide Sidebars (Lyrics + Feed) automatisch erscheinen
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

### [open] Phasenleiste inkonsistent zwischen progressiven und adaptiven Downloads
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Box 1 zeigt 3 Phasen (Auflösen · Video · Abschluss), Box 2 zeigt 5 (+ Audio + Merge). Optisch verwirrend.
- **Vermutete Ursache:** Phasen werden dynamisch erzeugt, aber die Darstellung signalisiert nicht, warum die eine Box weniger Phasen hat.
- **Prio:** 🟡 niedrig (technisch korrekt, aber UX-Reibung)

### [open] UI zeigt falsche Phase: "Video" während Audio lädt
- **Bereich:** frontend (DownloadQueue) + backend (`_on_progress`)
- **Symptom:** Audio-Download läuft bereits, Queue-Box behauptet weiter "Video wird heruntergeladen".
- **Vermutete Ursache:** Phase-Umschaltung zwischen Video- und Audio-Download wird nicht zuverlässig via WS gebroadcastet — vermutlich Race oder WS_THROTTLE verschluckt die Phasen-Änderung.
- **Prio:** 🔴 hoch (irreführt beim Überwachen von Downloads)

### [open] Keine ETA / Restzeit-Schätzung
- **Bereich:** frontend (DownloadQueue)
- **Symptom:** Es gibt nur `bytes_done/bytes_total` und Prozent — keine Schätzung der verbleibenden Zeit basierend auf bisherigem Durchsatz.
- **Vermutete Ursache:** ETA wird nicht berechnet/gebroadcastet.
- **Prio:** 🟠 mittel

### [open] RSS-Feed von YouTube 404 für alle Kanäle
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

### [open] Unerreichbare Videos gehen in Endlos-Retry
- **Bereich:** backend (download queue)
- **Symptom:** Videos mit dauerhaften Fehlern (deleted, private, members-only, region-blocked) retryen weiter bis max_retries.
- **Lösung:** Fehlerarten klassifizieren, dauerhafte Fehler → Status setzen (`unavailable`, `private`, `members_only`, `region_blocked`). Skip-Logik + Editierbarkeit im Frontend pro Kanal.
- **Prio:** 🔴 hoch

### [open] Job-Tracking unsauber: Zombie-Jobs, parallele Läufe, vermutete Mehrfach-Implementierung
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

### [open] 156 Alt-Jobs in der Queue aus pytubefix-Ära
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
