#!/usr/bin/env bash
#
# TubeVault - Sicherung der Datenbank nach der Sicherungsregel.
#
# Ruft die Schnittstelle (VACUUM INTO nach exports/backups/tubevault_backup_*.db). Ob eine neue Sicherung entsteht,
# entscheidet die App selbst (backend/app/services/sicherung.py, Werte in backend/app/config.py, überschreibbar in der
# .env): regelmäßig frühestens am sicherung_abstand_tage-ten Kalendertag nach der jüngsten, vor dem Ausrollen nur, wenn
# die jüngste älter ist als sicherung_vor_ausrollen_ab_stunden, nie ohne Änderung; jeder Lauf hält höchstens
# sicherung_behalten Stände. Eine frische Sicherung prüft das Skript mit PRAGMA integrity_check.
#
#   backup_db.sh                   regelmäßig (Zeitplan)
#   backup_db.sh --vor-ausrollen   vor dem Ausrollen, solange die bisherige Fassung noch läuft
#
# Cron (sonntags 03:00), <klon> ist der Ordner des Klons:
#   0 3 * * 0 <klon>/scripts/backup_db.sh >> <klon>/logs/backup.log 2>&1
#
set -euo pipefail

case "${1:-}" in
  "") ANLASS=regelmaessig ;;
  --vor-ausrollen) ANLASS=ausrollen ;;
  *) echo "Aufruf: $0 [--vor-ausrollen]" >&2; exit 64 ;;
esac

KLON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=umgebung.sh
. "$KLON/scripts/umgebung.sh"
# Ordner der Medien wie in docker-compose.yml: TUBEVAULT_MEDIEN aus der .env des Klons
MEDIEN="${TUBEVAULT_MEDIEN:-$(env_wert TUBEVAULT_MEDIEN)}"
[ -n "$MEDIEN" ] || { echo "TUBEVAULT_MEDIEN fehlt in $KLON/.env"; exit 1; }

API="http://127.0.0.1:8031"   # nicht localhost: das führt auf dem Pi zu ::1, dort lauscht der Container nicht
BACKUP_DIR="$MEDIEN/exports/backups"   # exports liegt bei den Medien (große Platte)
LOG_DIR="$KLON/logs"

mkdir -p "$LOG_DIR"
ts() { date '+%F %T'; }
feld() { printf '%s' "$RESP" | sed -n "s/.*\"$1\"[ :]*\"\([^\"]*\)\".*/\1/p"; }

echo "[$(ts)] Sicherungslauf startet ($ANLASS)"

# 1. Lauf über die Schnittstelle: sie entscheidet, legt bei Bedarf an und räumt auf
RESP=$(curl -s -X POST "$API/api/backup/create?anlass=$ANLASS&frontend_version=cron" || true)
AUSGANG=$(feld ausgang)
if [ -z "$AUSGANG" ]; then
    echo "[$(ts)] FEHLER: die Schnittstelle antwortet nicht wie erwartet. Antwort: $RESP"
    exit 1
fi
echo "[$(ts)] $(feld meldung)"
if [ "$AUSGANG" != "angelegt" ]; then
    echo "[$(ts)] Sicherungslauf fertig"
    exit 0
fi

FILE=$(feld filename)
BK="$BACKUP_DIR/$FILE"
if [ ! -s "$BK" ]; then
    echo "[$(ts)] FEHLER: Sicherung fehlt/leer: $BK"
    exit 2
fi

# 2. Integrität der frischen Sicherung prüfen
if command -v sqlite3 >/dev/null 2>&1; then
    CHK=$(sqlite3 "$BK" "PRAGMA integrity_check;" 2>&1 | head -1)
    if [ "$CHK" != "ok" ]; then
        echo "[$(ts)] FEHLER: integrity_check = '$CHK' für $FILE"
        exit 3
    fi
    NV=$(sqlite3 "$BK" "SELECT COUNT(*) FROM videos;" 2>/dev/null || echo '?')
    echo "[$(ts)] OK: $FILE ($(du -h "$BK" | cut -f1), integrity=ok, videos=$NV)"
else
    echo "[$(ts)] OK: $FILE ($(du -h "$BK" | cut -f1)) - sqlite3 fehlt, integrity ungeprüft"
fi

echo "[$(ts)] Sicherungslauf fertig"
