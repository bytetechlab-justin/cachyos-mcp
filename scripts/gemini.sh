#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
GEMINI_BIN="$PROJECT_DIR/.clients/gemini/node_modules/.bin/gemini"
if [ ! -x "$GEMINI_BIN" ]; then
    echo 'Gemini CLI is not installed. Run npm ci --prefix ~/Projects/cachyos-mcp/.clients/gemini in a host terminal.' >&2
    exit 1
fi
if [ -f /.flatpak-info ]; then
    exec /usr/bin/flatpak-spawn --host "$GEMINI_BIN" "$@"
fi
exec "$GEMINI_BIN" "$@"
