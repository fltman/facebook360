#!/bin/bash
# FB360 Viewer - Lokal server

PORT=${1:-8360}
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                    FB360 360° Viewer                          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "  🌐 http://localhost:$PORT/viewer.html"
echo ""
echo "  Dra en 360-bild till webbläsaren för att visa den."
echo "  Tryck Ctrl+C för att avsluta."
echo ""

# Öppna i webbläsare
open "http://localhost:$PORT/viewer.html" 2>/dev/null || \
xdg-open "http://localhost:$PORT/viewer.html" 2>/dev/null &

# Starta server
cd "$DIR"
python3 -m http.server $PORT
