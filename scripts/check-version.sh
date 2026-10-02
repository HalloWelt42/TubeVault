#!/bin/bash
# TubeVault: Prüft, dass Quelle und Spiegel dieselbe Version tragen.
set -euo pipefail
cd "$(dirname "$0")/.."

SOURCE=$(sed -n 's/.*"version": *"\([0-9.]*\)".*/\1/p' version.json)
BACKEND=$(sed -n 's/^VERSION = "\([0-9.]*\)".*/\1/p' backend/app/config.py)
FRONTEND=$(sed -n 's/.*"version": *"\([0-9.]*\)".*/\1/p' frontend/package.json | head -1)

if [ -z "$SOURCE" ] || [ "$SOURCE" != "$BACKEND" ] || [ "$SOURCE" != "$FRONTEND" ]; then
  echo "Versionen laufen auseinander:" >&2
  echo "  version.json            $SOURCE" >&2
  echo "  backend/app/config.py   $BACKEND" >&2
  echo "  frontend/package.json   $FRONTEND" >&2
  echo "Beheben mit: scripts/set-version.sh <Version> oder scripts/bump.sh patch|minor" >&2
  exit 1
fi
echo "$SOURCE"
