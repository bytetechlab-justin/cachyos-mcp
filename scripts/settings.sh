#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f /.flatpak-info ]; then
    exec /usr/bin/flatpak-spawn --host --env=QT_QPA_PLATFORM=wayland --env=QT_PLUGIN_PATH= --env=QT_QPA_PLATFORM_PLUGIN_PATH= --env=PYTHONPATH= "$PROJECT_DIR/.venv/bin/python" -m cachyos_mcp.gui.app "$@"
fi
exec "$PROJECT_DIR/.venv/bin/python" -m cachyos_mcp.gui.app "$@"
