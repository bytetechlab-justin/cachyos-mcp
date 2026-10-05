#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /.flatpak-info ]; then
    exec /usr/bin/flatpak-spawn --host "$PROJECT_DIR/.venv/bin/python" -m cachyos_mcp.server --config "$PROJECT_DIR/config/settings.toml"
fi
exec "$PROJECT_DIR/.venv/bin/python" -m cachyos_mcp.server --config "$PROJECT_DIR/config/settings.toml"
