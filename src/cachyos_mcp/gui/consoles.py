"""Fixed, user-clicked client launch actions; no model-supplied commands."""

import os
import shutil
from pathlib import Path

from ..config import PROJECT
from ..executor import Executor

CLIENTS = {"Claude Code": "claude", "Gemini CLI": "gemini", "Codex": "codex"}


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
        result = self.executor.launch_desktop(
            [terminal, "--workdir", str(PROJECT), "--hold", "-e", executable], str(PROJECT)
        )
        if not result["success"]:
            result["message"] = "Konsole could not start. Check your desktop session and try again."
        return result
