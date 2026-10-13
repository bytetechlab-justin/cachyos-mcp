#!/bin/bash
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f /.flatpak-info ]; then
    exec flatpak-spawn --host --env=QT_PLUGIN_PATH= --env=QT_QPA_PLATFORM_PLUGIN_PATH= --env=PYTHONPATH= bash "$APP_DIR/launch.sh" "$@"
fi
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    echo 'Run bash install.sh in the Cachy Canvas folder first.' >&2
    exit 1
fi
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/app.py" "$@"
