#!/usr/bin/env bash
# Einrichten von TubeVault. Schritte und Proben der Neueinrichtung stehen in HANDBUCH.md.
#
#   ./einrichten.sh                                       im Klon auf dem Pi: braucht die .env (Vorlage .env.example),
#                                                         legt die Ordner unter TUBEVAULT_INDEX und TUBEVAULT_MEDIEN an,
#                                                         baut und startet (docker compose up -d --build: Backend,
#                                                         Oberfläche, Token-Dienst, Nachvertoner)
#   ./einrichten.sh --probe --ziel DIR --port-versatz N   Probelauf des Handbuchs: Backend und Oberfläche aus DIR mit
#                                                         einer .env, deren Ordner in DIR liegen, eigenen Namen, Backend
#                                                         abgeschottet, Port der Oberfläche um N verschoben und nur an
#                                                         127.0.0.1 (deploy/probelauf.compose.yml)
#   ./einrichten.sh --probe --ziel DIR --abbauen          entfernt Container, Netze und die gebauten Abbilder
set -euo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARTEN_S=240
PROBE_COMPOSE=(-f docker-compose.yml -f deploy/probelauf.compose.yml)
ORDNER_INDEX=(data thumbnails avatars metadata banners nachvertoner)
ORDNER_MEDIEN=(videos audio subtitles exports)

# Ordner, die docker-compose.yml einhängt, unter Index und Medien aus der .env von $KLON
ordner_anlegen() {
  local index medien o
  index="$(env_wert TUBEVAULT_INDEX)"
  medien="$(env_wert TUBEVAULT_MEDIEN)"
  if [ -z "$index" ] || [ -z "$medien" ]; then
    echo "TUBEVAULT_INDEX und TUBEVAULT_MEDIEN fehlen in $KLON/.env (Vorlage .env.example)" >&2
    return 1
  fi
  for o in "${ORDNER_INDEX[@]}"; do mkdir -p "$index/$o"; done
  for o in "${ORDNER_MEDIEN[@]}"; do mkdir -p "$medien/$o"; done
}

einrichten() {
  KLON="$HIER"
  # shellcheck source=scripts/umgebung.sh
  . "$KLON/scripts/umgebung.sh"
  [ -f "$KLON/.env" ] || { echo "Erst die .env anlegen: cp .env.example .env, dann Ordner und Adressen eintragen" >&2; exit 1; }
  ordner_anlegen
  cd "$KLON"
  docker compose up -d --build
  echo "TubeVault läuft: Oberfläche Port 8032, Schnittstelle Port 8031 (docker compose ps)"
}

# veröffentlichter Port der Oberfläche laut docker-compose.yml (er steht nur dort)
grundport() {
  docker compose -f "$1/docker-compose.yml" config --format json | python3 -c '
import json, sys
print(json.load(sys.stdin)["services"]["tubevault-frontend"]["ports"][0]["published"])'
}

probe_aufbauen() {
  local ziel="$1" versatz="$2" port
  KLON="$ziel"
  # shellcheck source=scripts/umgebung.sh
  . "$KLON/scripts/umgebung.sh"
  mkdir -p "$ziel/config" "$ziel/probe-nachvertoner"
  touch "$ziel/probe-nachvertoner/schluessel" "$ziel/probe-nachvertoner/rootCA.pem"
  # die .env des Betriebs, nur mit Ordnern im Probeordner; der Nachvertoner startet im Probelauf nicht
  {
    echo "TUBEVAULT_INDEX=$ziel/index"
    echo "TUBEVAULT_MEDIEN=$ziel/medien"
    echo "NACHVERTONER_SCHLUESSEL=$ziel/probe-nachvertoner/schluessel"
    echo "NACHVERTONER_CA=$ziel/probe-nachvertoner/rootCA.pem"
    echo "NACHVERTONER_VERTONUNG=http://127.0.0.1:9"
    echo "NACHVERTONER_KELLERWOLKE=http://127.0.0.1:9"
  } > "$ziel/.env"
  ordner_anlegen
  port=$(( $(grundport "$ziel") + versatz ))
  echo "PROBE_PORT=$port" >> "$ziel/.env"
  cd "$ziel"
  if ! docker compose "${PROBE_COMPOSE[@]}" up -d --build --quiet-pull tubevault-backend tubevault-frontend; then
    docker compose "${PROBE_COMPOSE[@]}" logs --tail 40 >&2 || true
    return 1
  fi
  local ende=$(( $(date +%s) + WARTEN_S ))
  while [ "$(date +%s)" -lt "$ende" ]; do
    if curl -sf "http://127.0.0.1:$port/api/system/health" >/dev/null; then
      echo "ANTWORTET http://127.0.0.1:$port/api/system/health"
      return 0
    fi
    sleep 2
  done
  echo "TubeVault antwortet nach $WARTEN_S s nicht" >&2
  docker compose "${PROBE_COMPOSE[@]}" logs --tail 40 >&2 || true
  return 1
}

probe_abbauen() {
  [ -f "$1/.env" ] || return 0
  cd "$1"
  docker compose "${PROBE_COMPOSE[@]}" down --volumes --remove-orphans --rmi local
}

probe=0; abbauen=0; ziel=""; versatz=""
while [ $# -gt 0 ]; do
  case "$1" in
    --probe) probe=1 ;;
    --abbauen) abbauen=1 ;;
    --ziel) ziel="${2:?--ziel braucht einen Ordner}"; shift ;;
    --port-versatz) versatz="${2:?--port-versatz braucht eine Zahl}"; shift ;;
    *) echo "unbekannte Angabe: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$probe" = 0 ]; then
  einrichten
elif [ -z "$ziel" ] || [ ! -d "$ziel" ]; then
  echo "--probe braucht --ziel mit einem vorhandenen Ordner" >&2; exit 2
elif [ "$abbauen" = 1 ]; then
  probe_abbauen "$(cd "$ziel" && pwd)"
else
  probe_aufbauen "$(cd "$ziel" && pwd)" "${versatz:?--port-versatz fehlt}"
fi
