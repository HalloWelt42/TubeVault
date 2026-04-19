#!/bin/bash
# TubeVault: Git-Hooks aktivieren
# Einmalig nach "git clone" ausführen. Hooks sind im Repo versioniert (.githooks/),
# aber git aktiviert sie nicht automatisch — das macht dieses Script.
#
# Usage:  bash .githooks/install.sh

set -e

cd "$(dirname "$0")/.."

git config --local core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/commit-msg .githooks/install.sh

echo "✅ Git-Hooks aktiviert (core.hooksPath = .githooks)"
echo "   Pre-Commit: blockiert 'claude'/'anthropic' in Inhalten + Dateinamen"
echo "   Commit-Msg: blockiert 'claude'/'anthropic' in Commit-Messages"
