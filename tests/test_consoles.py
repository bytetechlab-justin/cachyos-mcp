"""Tray terminal launches use explicit argv and leave client sessions independent."""

import pytest

pytest.importorskip("PySide6")

from cachyos_mcp.config import PROJECT, Settings
from cachyos_mcp.executor import Executor
from cachyos_mcp.gui.consoles import ConsoleLauncher


@pytest.mark.parametrize(
    "client,command", [("Claude Code", "claude"), ("Gemini CLI", "gemini"), ("Codex", "codex")]
)
def test_clients_launch_without_shell(monkeypatch, client, command):
    calls = []
    from cachyos_mcp.gui import consoles

    # Spaces and shell characters must stay a single executable argument.
    executable = "/home/user/my clients/" + command + ";literal"
    monkeypatch.setattr(
        consoles.shutil,
        "which",
        lambda name, **kwargs: "/usr/bin/konsole" if name == "konsole" else executable,
    )
    monkeypatch.setattr(
        Executor,
        "launch_desktop",
        lambda self, argv, cwd: calls.append((argv, cwd)) or {"success": True, "pid": 123},
    )
    result = ConsoleLauncher(Settings()).open(client)
    assert result["success"]
    argv, cwd = calls[0]
    assert argv[-1] == executable
    assert argv[argv.index("-e") + 1 :] == [executable]
    assert cwd == str(PROJECT)
    assert "--hold" in argv
    assert not any(value in {"sh", "bash", "-c"} for value in argv)


def test_missing_client_does_not_launch(monkeypatch):
    from cachyos_mcp.gui import consoles

    monkeypatch.setattr(
        consoles.shutil,
        "which",
        lambda name, **kwargs: "/usr/bin/konsole" if name == "konsole" else None,
    )
    monkeypatch.setattr(
        Executor, "launch_desktop", lambda *a: pytest.fail("No launch for missing client")
    )
    result = ConsoleLauncher(Settings()).open("Codex")
    assert not result["success"]
    assert "Codex" in result["message"]
