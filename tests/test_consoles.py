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
    client_argv = argv[argv.index("-e") + 1 :]
    assert client_argv[0] == executable
    if client == "Claude Code":
        import json

        assert client_argv[1] == "--settings"
        status = json.loads(client_argv[2])["statusLine"]
        assert status["type"] == "command"
        assert "cachyos_mcp.gui.usage_relay" in status["command"]
    else:
        assert client_argv == [executable]
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


def test_claude_relay_preserves_statusline_without_writing(tmp_path, monkeypatch):
    import json
    import shlex

    from cachyos_mcp.gui import consoles

    monkeypatch.setattr(consoles.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(consoles, "PROJECT", tmp_path / "project")
    directory = tmp_path / ".claude"
    directory.mkdir()
    path = directory / "settings.json"
    command = "printf '%s' 'my status; literal'"
    original = json.dumps({"statusLine": {"type": "command", "command": command}})
    path.write_text(original)
    settings = consoles.claude_usage_settings()
    argv = shlex.split(settings["statusLine"]["command"])
    assert argv[-1] == command
    assert path.read_text() == original


def fake_proc(root, entries):
    for pid, (parent, argv) in entries.items():
        directory = root / str(pid)
        directory.mkdir()
        (directory / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        (directory / "stat").write_bytes(f"{pid} (a b) c) S {parent} 1 1".encode())
    (root / "self").mkdir()
    return root


def test_processes_match_fixed_clients_and_skip_own_children(tmp_path):
    from cachyos_mcp.gui import consoles

    proc = fake_proc(
        tmp_path,
        {
            10: (1, ["/usr/bin/konsole", "--hold", "-e", "/home/user/.local/bin/claude"]),
            11: (10, ["/home/user/.local/bin/claude", "--settings", "{}"]),
            12: (11, ["/usr/bin/zsh", "-c", "codex --help"]),
            20: (1, ["node", "--no-warnings", "/usr/bin/gemini"]),
            21: (1, ["node", "/srv/app/server.js", "gemini"]),
            30: (1, ["/opt/codex/bin/codex", "app-server"]),
            31: (30, ["/opt/codex/bin/codex-code-mode-host"]),
            # The settings app's own quota poller and its native child.
            40: (1, ["python", "-m", "cachyos_mcp.gui.app"]),
            41: (40, ["node", "/usr/bin/codex", "app-server"]),
            42: (41, ["/usr/lib/codex/bin/codex", "app-server"]),
        },
    )
    assert consoles.processes(exclude={40}, proc=proc) == {
        "Claude Code": [11],
        "Gemini CLI": [20],
        "Codex": [30],
    }


def test_shut_down_signals_only_the_selected_client(monkeypatch):
    import signal

    from cachyos_mcp.gui import consoles

    found = {"Claude Code": [11, 12], "Gemini CLI": [20], "Codex": [30]}
    sent = []
    monkeypatch.setattr(consoles, "processes", lambda: found)
    monkeypatch.setattr(consoles.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert consoles.shut_down("Claude Code") == [11, 12]
    assert sent == [(11, signal.SIGTERM), (12, signal.SIGTERM)]
    # The kill follow-up never reaches a process that was not signalled first.
    assert consoles.shut_down("Claude Code", signal.SIGKILL, [12, 99]) == [12]
    assert consoles.shut_down("sh -c arbitrary-command") == []
    assert len(sent) == 3


def test_visibility_persists_per_client(tmp_path):
    from PySide6.QtCore import QSettings

    from cachyos_mcp.gui.consoles import AgentVisibility

    path = str(tmp_path / "preferences.ini")
    visibility = AgentVisibility(QSettings(path, QSettings.Format.IniFormat))
    assert all(visibility.visible(client) for client in ["Claude Code", "Gemini CLI", "Codex"])
    visibility.set_visible("Gemini CLI", False)
    visibility.store.sync()
    reloaded = AgentVisibility(QSettings(path, QSettings.Format.IniFormat))
    assert not reloaded.visible("Gemini CLI")
    assert reloaded.visible("Codex")
