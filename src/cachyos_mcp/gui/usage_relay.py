"""Claude status-line bridge: forward quota fields only, preserve an existing command."""

import argparse
import json
import subprocess
import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from .usage import OBJECT_PATH, SERVICE, claude_windows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", default="")
    args = parser.parse_args()
    raw = sys.stdin.read(1048576)
    try:
        data = json.loads(raw)
    except ValueError:
        return 0
    app = QCoreApplication.instance() or QCoreApplication([])
    # Strip the prompt, transcript path, working directory and all unrelated fields.
    values = claude_windows(data)
    payload = {
        "rate_limits": {
            key: {"used_percentage": value["used"], "resets_at": value["resets_at"]}
            for key, value in values.items()
            if value
        }
    }
    interface = QDBusInterface(SERVICE, OBJECT_PATH, SERVICE, QDBusConnection.sessionBus())
    interface.setTimeout(500)
    interface.call("SubmitClaude", json.dumps(payload))
    if args.previous:
        # This is the user's existing status-line shell command, never model-generated input.
        try:
            subprocess.run(args.previous, shell=True, input=raw, text=True, timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        model = data.get("model", {}) if isinstance(data, dict) else {}
        print(
            model.get("display_name", "Claude Code") if isinstance(model, dict) else "Claude Code"
        )
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
