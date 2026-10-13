#!/bin/bash
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f /.flatpak-info ]; then
    exec flatpak-spawn --host --env=PYTHONPATH= bash "$APP_DIR/install.sh" "$@"
fi
# A private Python avoids Arch's rolling system Python and package environment.
UV_BIN=$(command -v uv || true)
if [ -z "$UV_BIN" ]; then
    echo 'Install uv first (sudo pacman -S uv), then rerun this script.' >&2
    exit 1
fi
"$UV_BIN" venv --python 3.12 "$APP_DIR/.venv"
"$UV_BIN" pip install --python "$APP_DIR/.venv/bin/python" torch --index-url https://download.pytorch.org/whl/cu128
"$UV_BIN" pip install --python "$APP_DIR/.venv/bin/python" -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" "$APP_DIR/diagnose.py"
"$APP_DIR/.venv/bin/python" "$APP_DIR/desktop.py"
echo 'Installed. Open Cachy Canvas from your application menu.'
