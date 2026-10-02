#!/bin/bash
# TubeVault: Quelle (version.json) und Spiegel auf eine Version setzen.
set -euo pipefail
cd "$(dirname "$0")/.."

NEW="${1:?Aufruf: scripts/set-version.sh X.Y.Z}"
printf '{\n  "version": "%s"\n}\n' "$NEW" > version.json
sed -i.bak -E "s/^VERSION = \"[0-9.]+\"/VERSION = \"$NEW\"/" backend/app/config.py
# package.json: nur das eigene Versionsfeld im Kopf der Datei
sed -i.bak -E "1,5s/\"version\": \"[0-9.]+\"/\"version\": \"$NEW\"/" frontend/package.json
rm -f backend/app/config.py.bak frontend/package.json.bak
scripts/check-version.sh
