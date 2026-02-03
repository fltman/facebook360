#!/bin/bash
# FB360 Server Starter
# Startar Flask-servern med AI-generering

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Aktivera venv om det finns
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Kolla efter .env fil
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Starta servern
python3 server.py "$@"
