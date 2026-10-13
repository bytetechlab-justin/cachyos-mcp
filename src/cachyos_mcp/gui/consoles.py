"""Fixed, user-clicked client launch actions; no model-supplied commands."""

import json
import os
import shlex
import shutil
import signal
import sys
from pathlib import Path

from ..config import PROJECT
from ..executor import Executor

CLIENTS = {"Claude Code": "claude", "Gemini CLI": "gemini", "Codex": "codex"}
# Script runtimes whose first non-option argument names the client.
RUNTIMES = {"node", "bun"}


class AgentVisibility:
    """Per-user taskbar preference; kept out of the agent policy file."""

    def __init__(self, store=None):
        self.store = store
        self.hidden = set()
        if store is not None:
            self.hidden = {
                client for client in CLIENTS if not store.value(self.key(client), True, type=bool)
            }

    @staticmethod
    def key(client):
        return "taskbar/show_" + CLIENTS[client]

    def visible(self, client):
        return client not in self.hidden

    def set_visible(self, client, visible):
        if client not in CLIENTS:
            return
        if visible:
            self.hidden.discard(client)
        else:
            self.hidden.add(client)
        if self.store is not None:
            self.store.setValue(self.key(client), bool(visible))


def processes(exclude=None, proc=Path("/proc")):
    """This user's live client processes by name, skipping `exclude` and its descendants.

    The settings app is excluded by default so its own Codex quota poller is never counted.
    """
    exclude = {os.getpid()} if exclude is None else set(exclude)
    parents, candidates = {}, []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            argv = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            parent = int((entry / "stat").read_bytes().rpartition(b")")[2].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        pid = int(entry.name)
        parents[pid] = parent
        name = os.path.basename(argv[0])
        if name in RUNTIMES:
            name = next((os.path.basename(a) for a in argv[1:] if not a.startswith("-")), "")
        candidates.append((pid, name))
    found = {client: [] for client in CLIENTS}
    for pid, name in candidates:
        client = next((c for c, command in CLIENTS.items() if command == name), None)
        if client is None:
            continue
        ancestor, seen = pid, set()
        while ancestor in parents and ancestor not in seen and ancestor not in exclude:
            seen.add(ancestor)
            ancestor = parents[ancestor]
        if ancestor not in exclude:
            found[client].append(pid)
    return found


def shut_down(client, sig=signal.SIGTERM, only=None):
    """Signal one fixed client's processes; `only` limits a follow-up to earlier targets."""
    if client not in CLIENTS:
        return []
    signalled = []
    for pid in processes()[client]:
        if only is not None and pid not in only:
            continue
        try:
            os.kill(pid, sig)
            signalled.append(pid)
        except OSError:
            continue
    return signalled


class ConsoleLauncher:
    def __init__(self, settings):
        self.executor = Executor(settings)

    def open(self, client: str) -> dict:
        if client not in CLIENTS:
            return {"success": False, "message": "Unknown console client"}
        host_path = os.pathsep.join(
            [str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"]
        )
        terminal = shutil.which("konsole", path=host_path)
        executable = shutil.which(CLIENTS[client], path=host_path)
        if terminal is None:
            return {
                "success": False,
                "message": "Konsole is not installed or available on the host.",
            }
        if executable is None:
            return {
                "success": False,
                "message": f"{client} is not installed or available on the host.",
            }
        argv = [terminal, "--workdir", str(PROJECT), "--hold", "-e", executable]
        if client == "Claude Code":
            argv.extend(["--settings", json.dumps(claude_usage_settings())])
        result = self.executor.launch_desktop(argv, str(PROJECT))
        if not result["success"]:
            result["message"] = "Konsole could not start. Check your desktop session and try again."
        return result


def claude_usage_settings():
    """Session-only status-line override; never rewrite the client's saved settings."""
    previous = ""
    for path in [
        Path.home() / ".claude/settings.json",
        PROJECT / ".claude/settings.json",
        PROJECT / ".claude/settings.local.json",
    ]:
        try:
            data = json.loads(path.read_text())
            status = data.get("statusLine", {})
            if isinstance(status, dict) and isinstance(status.get("command"), str):
                previous = status["command"]
        except (OSError, ValueError, AttributeError):
            continue
    command = shlex.join(
        [sys.executable, "-m", "cachyos_mcp.gui.usage_relay", "--previous", previous]
    )
    return {"statusLine": {"type": "command", "command": command}}
