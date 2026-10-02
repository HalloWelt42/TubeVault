#!/bin/bash
# TubeVault: Version erhöhen.
#
# version.json ist die eine Quelle. Backend (backend/app/config.py) und
# Frontend (frontend/package.json) tragen Spiegel, weil ihre Container nur den
# eigenen Ordner sehen. Dieses Skript setzt Quelle und Spiegel gemeinsam.
#
# Aufruf:  scripts/bump.sh patch   (Fehlerbehebung, +0.0.1)
#          scripts/bump.sh minor   (neue Funktion, +0.1.0)
#          scripts/bump.sh major
set -euo pipefail
cd "$(dirname "$0")/.."

PART="${1:-}"
CURRENT=$(sed -n 's/.*"version": *"\([0-9.]*\)".*/\1/p' version.json)
IFS=. read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$PART" in
  patch) PATCH=$((PATCH + 1)) ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  *) echo "Aufruf: scripts/bump.sh patch|minor|major" >&2; exit 2 ;;
esac
NEW="$MAJOR.$MINOR.$PATCH"

scripts/set-version.sh "$NEW"
echo "Version: $CURRENT -> $NEW"
