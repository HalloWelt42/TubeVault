#!/usr/bin/env bash
# Werte aus der .env des Klons (dieselbe Datei, die docker compose liest), zum Einbinden mit ". scripts/umgebung.sh".
# Erwartet KLON (Ordner des Klons); env_wert NAME gibt den letzten Wert von NAME aus, ohne Anführungszeichen, oder nichts.
env_wert() {
  sed -n "s/^$1=//p" "$KLON/.env" 2>/dev/null | tail -n 1 | tr -d "\"'" || true
}
