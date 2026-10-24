#!/usr/bin/env bash
#
# TubeVault – Wöchentliches DB-Backup mit Rotation.
#
# Ruft den Backup-Endpoint (VACUUM INTO → exports/backups/tubevault_backup_*.db)
# und behält die letzten 8 Wochen-Backups.
# Verifiziert jedes frische Backup mit PRAGMA integrity_check.
#
# Cron (sonntags 03:00), <klon> ist der Ordner des Klons:
#   0 3 * * 0 <klon>/scripts/backup_db.sh >> <klon>/logs/backup.log 2>&1
#
set -euo pipefail

KLON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=umgebung.sh
. "$KLON/scripts/umgebung.sh"
# Ordner der Medien wie in docker-compose.yml: TUBEVAULT_MEDIEN aus der .env des Klons
MEDIEN="${TUBEVAULT_MEDIEN:-$(env_wert TUBEVAULT_MEDIEN)}"
[ -n "$MEDIEN" ] || { echo "TUBEVAULT_MEDIEN fehlt in $KLON/.env"; exit 1; }

API="http://127.0.0.1:8031"   # nicht localhost: das führt auf dem Pi zu ::1, dort lauscht der Container nicht
BACKUP_DIR="$MEDIEN/exports/backups"   # exports liegt bei den Medien (große Platte)
LOG_DIR="$KLON/logs"
KEEP=8                                              # letzte N Wochen-Backups behalten

mkdir -p "$LOG_DIR"
ts() { date '+%F %T'; }

echo "[$(ts)] Backup-Lauf startet"

# 1. DB-Backup via API (VACUUM INTO – konsistent, ohne WAL-Reste)
RESP=$(curl -s -X POST "$API/api/backup/create?frontend_version=cron" || true)
FILE=$(printf '%s' "$RESP" | sed -n 's/.*"filename"[ :]*"\([^"]*\)".*/\1/p')
if [ -z "$FILE" ]; then
    echo "[$(ts)] FEHLER: Backup-Endpoint lieferte keinen Dateinamen. Antwort: $RESP"
    exit 1
fi
BK="$BACKUP_DIR/$FILE"
if [ ! -s "$BK" ]; then
    echo "[$(ts)] FEHLER: Backup-Datei fehlt/leer: $BK"
    exit 2
fi

# 2. Integrität prüfen
if command -v sqlite3 >/dev/null 2>&1; then
    CHK=$(sqlite3 "$BK" "PRAGMA integrity_check;" 2>&1 | head -1)
    if [ "$CHK" != "ok" ]; then
        echo "[$(ts)] FEHLER: integrity_check = '$CHK' für $FILE"
        exit 3
    fi
    NV=$(sqlite3 "$BK" "SELECT COUNT(*) FROM videos;" 2>/dev/null || echo '?')
    echo "[$(ts)] OK: $FILE ($(du -h "$BK" | cut -f1), integrity=ok, videos=$NV)"
else
    echo "[$(ts)] OK: $FILE ($(du -h "$BK" | cut -f1)) – sqlite3 fehlt, integrity ungeprüft"
fi

# 3. Rotation – nur die letzten $KEEP DB-Backups behalten
cd "$BACKUP_DIR"
ls -1t tubevault_backup_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f -- "$old"; echo "[$(ts)] rotiert (gelöscht): $old"
done

echo "[$(ts)] Backup-Lauf fertig"
