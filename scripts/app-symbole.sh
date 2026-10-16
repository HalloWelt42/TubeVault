#!/bin/bash
# TubeVault: Fassungen des App-Symbols aus frontend/public/app-symbol.svg.
#
# iOS nimmt für den Homescreen nur PNG (apple-touch-icon, 180 px), das
# Manifest braucht 192 und 512 px. Der Browser-Tab bekommt favicon.svg:
# freigestellt (ohne den Grund) und auf das Gerät zugeschnitten. Die SVG ist
# die eine Quelle; nach einer Änderung daran dieses Skript laufen lassen und
# alle Fassungen mit einchecken.
# Gerastert wird mit dem kopflosen Chrome des Macs.
#
# Aufruf:  scripts/app-symbole.sh
set -euo pipefail
cd "$(dirname "$0")/../frontend/public"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SOURCE="$PWD/app-symbol.svg"

# Browser-Tab: ohne Grund, Ausschnitt um das Gerät (Antenne bis Füße)
sed -e '/<!--/,/-->/d' -e '/<defs>/,/<\/defs>/d' -e '/class="grund"/d' \
    -e 's/viewBox="0 0 512 512"/viewBox="58 53 396 396"/' \
    -e '1a\
  <!-- Erzeugt von scripts/app-symbole.sh aus app-symbol.svg: dort ändern. -->' "$SOURCE" > favicon.svg
echo "favicon.svg (freigestellt)"

# Chrome hat eine Mindestfenstergröße; kleinere Fassungen daher aus der
# 512er verkleinern (sips liegt jedem Mac bei)
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=512,512 --screenshot="$PWD/app-symbol-512.png" "file://$SOURCE" >/dev/null 2>&1
echo "app-symbol-512.png (512 px)"

shrink() {   # Größe, Zieldatei
  sips -z "$1" "$1" app-symbol-512.png --out "$2" >/dev/null
  echo "$2 ($1 px)"
}
shrink 192 app-symbol-192.png
shrink 180 apple-touch-icon.png
