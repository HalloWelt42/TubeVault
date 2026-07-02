#!/usr/bin/env bash
#
# TubeVault – Wöchentliches DB-Backup mit Rotation.
#
# Ruft den Backup-Endpoint (VACUUM INTO → exports/backups/tubevault_backup_*.db),
# sichert zusätzlich scan_index.db, und behält die letzten 8 Wochen-Backups.
# Verifiziert jedes frische Backup mit PRAGMA integrity_check.
#
# Cron (sonntags 03:00):
#   0 3 * * 0 /home/pi/tubevault/scripts/backup_db.sh >> /home/pi/tubevault/logs/backup.log 2>&1
#
set -euo pipefail

API="http://localhost:8031"
BACKUP_DIR="/mnt/tb26/tubevault/exports/backups"   # exports liegt auf tb26 (nicht /mnt/data)
SCAN_DB="/mnt/data/tubevault/data/db/scan_index.db"
LOG_DIR="/home/pi/tubevault/logs"
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

# 3. scan_index.db mitsichern (Zeitstempel aus DB-Backup-Namen ableiten)
STAMP=$(printf '%s' "$FILE" | sed -n 's/tubevault_backup_\([0-9]*_[0-9]*\)_.*/\1/p')
if [ -f "$SCAN_DB" ] && [ -n "$STAMP" ]; then
    cp -p "$SCAN_DB" "$BACKUP_DIR/scan_index_${STAMP}.db"
    echo "[$(ts)] scan_index gesichert: scan_index_${STAMP}.db"
fi

# 4. Rotation – nur die letzten $KEEP DB-Backups + scan_index behalten
cd "$BACKUP_DIR"
ls -1t tubevault_backup_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f -- "$old"; echo "[$(ts)] rotiert (gelöscht): $old"
done
ls -1t scan_index_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f -- "$old"
done

echo "[$(ts)] Backup-Lauf fertig"
