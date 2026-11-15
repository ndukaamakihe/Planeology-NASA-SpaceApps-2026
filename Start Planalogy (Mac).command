#!/bin/bash
# Planalogy: double-click to start. Opens the app in your browser; close this window to stop.
cd "$(dirname "$0")/web/app" || exit 1
PORT=8642
while lsof -i :$PORT >/dev/null 2>&1; do PORT=$((PORT+1)); done
(sleep 1; open "http://localhost:$PORT/" 2>/dev/null || xdg-open "http://localhost:$PORT/") &
echo "PLANALOGY is running at http://localhost:$PORT/  (close this window to stop)"
exec python3 -m http.server $PORT --bind 127.0.0.1
