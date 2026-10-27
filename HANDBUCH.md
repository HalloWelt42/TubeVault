---
zweck: "Das eigene Videoarchiv: Kanäle abonnieren, Videos und Ton laden, ansehen, hören und durchsuchen; dazu Musik und alte eigene Videos, auf Wunsch nachvertont."
geraet: [pi]
abhaengigkeiten: [kellerwolke, leitstelle, vertonung]
daten:
  - "Pi: Index unter `{{umgebung:TUBEVAULT_INDEX}}` (`data/` mit der Datenbank, rund 13 GB; `thumbnails/`, `avatars/`, `metadata/`, `banners/`, `nachvertoner/`)"
  - "Pi: Medien unter `{{umgebung:TUBEVAULT_MEDIEN}}` (`videos/`, `audio/`, `subtitles/`, `exports/` mit den Sicherungen der Datenbank)"
  - "Pi: `{{wurzel}}/config` (Laufzeit-Konfiguration, Anmeldedaten der Videoplattform) und `{{wurzel}}/.env` (Ordner und Adressen des Betriebs)"
sicherung:
  - "die Datenbank sichert `scripts/backup_db.sh` über die Schnittstelle nach `{{umgebung:TUBEVAULT_MEDIEN}}/exports/backups`: ein Zeitplan auf dem Pi ruft es sonntags um 3 Uhr, eine neue entsteht frühestens am siebten Kalendertag nach der jüngsten; vor dem Ausrollen `scripts/backup_db.sh --vor-ausrollen`, das nur sichert, wenn die jüngste älter als 24 Stunden ist; nie ohne Änderung; höchstens drei Stände (Vorgaben in `backend/app/config.py`, in der `.env` überschreibbar)"
  - "das Werkzeug Sicherungen holt die Sicherungen aus `exports/backups` auf den Mac. Videos, Ton und Untertitel werden nicht gesichert"
schluessel_orte:
  - "Pi: `{{wurzel}}/config/cookies.txt` (Anmeldung bei der Videoplattform, nicht im Repo)"
  - "Pi: `{{umgebung:NACHVERTONER_SCHLUESSEL}}`, Modus 0600 (App-Schlüssel des Nachvertoners bei der Kellerwolke)"
  - "Datenbank: Schlüssel der Leitstelle in den Einstellungen von TubeVault"
einrichten: einrichten.sh
stand: 6a1aa85
---

# TubeVault

## Zweck

TubeVault ist das Videoarchiv für zu Hause: Kanäle abonnieren, Videos und Ton laden, ansehen, hören und durchsuchen,
dazu die eigene Musiksammlung und alte eigene Videos. Die Datenbank ist nur der Index; Beschreibungen, Kapitel und
Notizen liegen als Dateien neben den Videos. KI-Aufgaben gehen über die [[Leitstelle]]. Der Nachvertoner holt Aufträge
von TubeVault und lässt sie über die [[Vertonung]] sprechen; er meldet sich mit einem App-Schlüssel der
[[Kellerwolke]] an.

Auf dem Pi laufen vier Container aus `docker-compose.yml` im Klon `{{wurzel}}`: Backend (Schnittstelle, Port
{{port:docker-compose.yml/tubevault-backend}}), Oberfläche (nginx, Port {{port:docker-compose.yml/tubevault-frontend}}),
der Token-Dienst für den Abruf und der Nachvertoner. Der Index liegt auf der schnellen Platte
(`{{umgebung:TUBEVAULT_INDEX}}`), die Medien auf der großen (`{{umgebung:TUBEVAULT_MEDIEN}}`). Beide Ordner und die
Angaben des Nachvertoners stehen in der `.env` neben `docker-compose.yml`, nie im Repo; ohne sie startet nichts.

## Was sie braucht

- Pi nach [[Grundlage Pi]] mit Docker, einer schnellen Platte für den Index und einer großen für die Medien; ffmpeg im
  System des Pi (der Nachvertoner nutzt es über eingehängte Dateien).
- [[Leitstelle]] für die KI (Einstellung der Route auf die Leitstelle mit ihrem Schlüssel).
- [[Vertonung]] und ein App-Zugang der [[Kellerwolke]] für den Nachvertoner.
- Anmeldedaten der Videoplattform in `config/cookies.txt`; ein Zeitplan auf dem Pi frischt sie alle sechs Stunden auf.

## Neu einrichten

Zwei Wege. Aus der Sicherung: die Datenbank (jüngste Kopie aus `exports/backups`) nach
`{{umgebung:TUBEVAULT_INDEX}}/data` zurückspielen, `config/` und die Schlüsseldatei des Nachvertoners zurücklegen; die
Medien bleiben auf der großen Platte. Frisch: leerer Index, Abos und Einstellungen neu; vorhandene Medien lassen sich
über den Scan wieder einordnen.

### 1. Klon auf dem Pi

```
git clone {{repo}} {{wurzel}}
```

Probe: `git -C {{wurzel}} log --oneline -1` nennt den Stand.

### 2. Ordner, Adressen und Zugänge

Im Klon `cp .env.example .env` und eintragen: `TUBEVAULT_INDEX`, `TUBEVAULT_MEDIEN` und die vier Angaben
`NACHVERTONER_*` (im Verbund gibt `handbuch ziel tubevault --env` die Zeilen aus); wahlweise `TUBEVAULT_SCAN_SOURCE`
und `TUBEVAULT_MUSIC_SOURCE`. Aus der Sicherung `config/` (mit `cookies.txt`) und die Schlüsseldatei zurücklegen.
Frisch: die Anmeldedaten der Videoplattform als `config/cookies.txt` ablegen, in der [[Kellerwolke]] einen App-Zugang
für den Nachvertoner anlegen und als einzige Zeile in `{{umgebung:NACHVERTONER_SCHLUESSEL}}` schreiben (Modus 0600).

Probe: `grep -c -E '^(TUBEVAULT_INDEX|TUBEVAULT_MEDIEN|NACHVERTONER_[A-Z]+)=' {{wurzel}}/.env` meldet 6,
`stat -c %a {{umgebung:NACHVERTONER_SCHLUESSEL}}` meldet 600, und `ls {{wurzel}}/config/cookies.txt` findet die Datei.

### 3. Einrichten und starten

`./einrichten.sh` im Klon: legt die Ordner unter `{{umgebung:TUBEVAULT_INDEX}}` und `{{umgebung:TUBEVAULT_MEDIEN}}`
an, baut und startet alle Container (`docker compose up -d --build`). Aus der Sicherung die Datenbank vorher nach
`{{umgebung:TUBEVAULT_INDEX}}/data` legen.

Probe: `curl -s http://127.0.0.1:{{port:docker-compose.yml/tubevault-backend}}/api/system/health` auf dem Pi antwortet,
und die Oberfläche auf Port {{port:docker-compose.yml/tubevault-frontend}} zeigt Bibliothek und Abos.

### 4. Zeitpläne auf dem Pi

Drei Einträge in der crontab des Benutzers, der TubeVault betreibt (`crontab -e`):

```
*/5 * * * * curl -sf -X POST "http://localhost:{{port:docker-compose.yml/tubevault-backend}}/api/subscriptions/tick" >> /tmp/tubevault-cron.log 2>&1
0 */6 * * * {{wurzel}}/scripts/refresh_cookies.sh >> {{wurzel}}/logs/cookies-refresh.log 2>&1
0 3 * * 0 {{wurzel}}/scripts/backup_db.sh >> {{wurzel}}/logs/backup.log 2>&1
```

Probe: `crontab -l` zeigt die drei Zeilen; nach fünf Minuten steht in `/tmp/tubevault-cron.log` kein Fehler.

### 5. Leitstelle und Nachvertoner

Frisch unter Einstellungen die Route der KI auf die [[Leitstelle]] stellen und ihren Schlüssel eintragen; in der
[[Vertonung]] dem Nachvertoner die Stimmen freigeben, die er nutzen darf.

Probe: `docker logs tubevault-nachvertoner` zeigt, dass er Aufträge abholt, und eine Frage an die KI in TubeVault bekommt
eine Antwort.

## Sicherung und Rückspielen

Die Datenbank sichert `scripts/backup_db.sh` über die Schnittstelle (`VACUUM INTO`) nach
`{{umgebung:TUBEVAULT_MEDIEN}}/exports/backups`; den Ordner liest das Skript aus der `.env`. Ob eine neue Sicherung
entsteht, entscheidet TubeVault selbst nach dem Alter der jüngsten, nicht der Takt des Aufrufs:

- regelmäßig (Zeitplan sonntags um 3 Uhr, Schritt 4): frühestens am siebten Kalendertag nach der jüngsten Sicherung;
- vor dem Ausrollen: im Klon `scripts/backup_db.sh --vor-ausrollen`, solange die bisherige Fassung noch läuft; es
  sichert nur, wenn die jüngste älter als 24 Stunden ist;
- von Hand: Einstellungen, Abschnitt System, "Jetzt sichern";
- nie ohne Änderung: sind Datenbank und `-wal` älter als die jüngste Sicherung, entsteht keine neue;
- jeder Lauf behält höchstens drei Stände (`tubevault_backup_*.db`, nach Änderungszeit), auch wenn keine neue entsteht;
  andere Dateien im Ordner fasst er nicht an.

Die Werte stehen in `backend/app/config.py`; in der `.env` überschreiben sie `TUBEVAULT_SICHERUNG_ABSTAND_TAGE`,
`TUBEVAULT_SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN` und `TUBEVAULT_SICHERUNG_BEHALTEN` (danach `docker compose up -d`). Was
ein Lauf getan hat, steht in `logs/backup.log`. Das Werkzeug Sicherungen holt den Ordner auf den Mac. Die Nutzerdaten
schreibt TubeVault zusätzlich täglich als Dateien nach `exports/userdata`. Videos, Ton und Untertitel auf der großen
Platte werden nicht gesichert.

Zurückspielen: `docker compose stop tubevault-backend`, die Sicherung als Datenbank nach
`{{umgebung:TUBEVAULT_INDEX}}/data` kopieren (Name wie die bisherige Datei), `docker compose start tubevault-backend`;
Probe wie in Schritt 3.

## Wenn etwas klemmt

- `docker compose` meldet "required variable ... is missing": die `.env` fehlt oder ihr fehlt eine Angabe (Schritt 2).
- Downloads scheitern: die Anmeldedaten sind abgelaufen (`logs/cookies-refresh.log`), oder der Token-Dienst läuft nicht
  (`docker compose ps`).
- Die wöchentliche Sicherung scheitert: `logs/backup.log`; die Schnittstelle unter Port
  {{port:docker-compose.yml/tubevault-backend}} muss auf dem Pi unter 127.0.0.1 antworten. Keine neue Sicherung ohne
  Fehler: `logs/backup.log` nennt den Grund (nicht fällig oder unverändert).
- Der Nachvertoner arbeitet nicht: Schlüsseldatei oder Zertifikat der Hausstelle fehlen (`docker logs tubevault-nachvertoner`),
  oder die Vertonung ist nicht erreichbar.
- Neue Netze lassen sich nicht anlegen: siehe [[Grundlage Pi]], Adressbereiche für Docker-Netze.
