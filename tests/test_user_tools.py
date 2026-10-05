from mcp import Client

from cachyos_mcp.config import Settings
from cachyos_mcp.server import create_server
from cachyos_mcp.tools.kde import desktop_quote, unit_quote


async def test_widget_and_git(tmp_path):
    settings = Settings(log_directory=str(tmp_path / "logs")).model_copy(
        update={
            "allowed_writable_directories": [str(tmp_path)],
            "allowed_project_directories": [str(tmp_path)],
        }
    )
    async with Client(create_server(settings)) as client:
        root = tmp_path / "widget"
        result = await client.call_tool(
            "create_plasma_widget_project",
            {"path": str(root), "name": "thermal", "confirmed": True},
        )
        assert result.structured_content["success"]
        assert (root / "contents/ui/main.qml").exists()
        result = await client.call_tool("git_init", {"path": str(root), "confirmed": True})
        assert result.structured_content["success"]
        result = await client.call_tool("git_status", {"path": str(root)})
        assert result.structured_content["success"]
        result = await client.call_tool(
            "git_add", {"path": str(root), "files": ["metadata.json"], "confirmed": True}
        )
        assert result.structured_content["success"]
        result = await client.call_tool(
            "git_add", {"path": str(root), "files": ["../escape"], "confirmed": True}
        )
        assert not result.structured_content["success"]


async def test_service_name_and_desktop_injection(tmp_path):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        result = await client.call_tool(
            "create_desktop_entry",
            {
                "name": "evil\nExec=sh",
                "executable": "/usr/bin/true",
                "arguments": [],
                "confirmed": True,
            },
        )
        assert not result.structured_content["success"]
        result = await client.call_tool(
            "restart_systemd_user_service", {"name": "dbus", "confirmed": True}
        )
        assert not result.structured_content["success"]
        result = await client.call_tool(
            "create_systemd_user_service",
            {
                "name": "x",
                "executable": "/usr/bin/true",
                "arguments": ["hello\nExecStart=/bin/sh"],
                "confirmed": True,
            },
        )
        assert not result.structured_content["success"]


def test_config_quotes():
    assert "%%" in desktop_quote("%f")
    assert "\\\\$" in desktop_quote("$HOME")
    assert unit_quote("%h") == '"%%h"'


async def test_host_generated_file_validation(tmp_path, monkeypatch):
    import shutil

    from cachyos_mcp.executor import Executor

    monkeypatch.setenv("HOME", str(tmp_path))
    settings = Settings(
        log_directory=str(tmp_path / "logs"),
        allowed_project_directories=[str(tmp_path / "Projects")],
        allowed_writable_directories=[
            str(tmp_path / "Projects"),
            str(tmp_path / ".local"),
            str(tmp_path / ".config"),
        ],
    )
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(
            "create_desktop_entry",
            {
                "name": "example",
                "executable": "/usr/bin/true",
                "arguments": ["a b", "$HOME", "%f", 'a"b', "back\\slash"],
                "confirmed": True,
            },
        )
        assert result.structured_content["success"]
        result = await client.call_tool(
            "create_systemd_user_service",
            {
                "name": "example",
                "executable": "/usr/bin/true",
                "arguments": ["a b", "$HOME", "%h"],
                "confirmed": True,
            },
        )
        assert result.structured_content["success"]
        result = await client.call_tool(
            "create_plasma_widget_project",
            {"name": "thermal", "path": str(tmp_path / "Projects/widget"), "confirmed": True},
        )
        assert result.structured_content["success"]
    commands = [
        [
            "systemd-analyze",
            "--user",
            "verify",
            str(tmp_path / ".config/systemd/user/cachyos-mcp-example.service"),
        ],
        ["qmlformat", "-n", str(tmp_path / "Projects/widget/contents/ui/main.qml")],
    ]
    if shutil.which("desktop-file-validate"):
        commands.append(
            ["desktop-file-validate", str(tmp_path / ".local/share/applications/example.desktop")]
        )
    for argv in commands:
        result = await Executor(settings).run(argv)
        assert result["success"], result


async def test_git_blocks_filters_and_metadata_symlinks(tmp_path):
    from cachyos_mcp.executor import Executor

    root = tmp_path / "project"
    root.mkdir()
    settings = Settings(log_directory=str(tmp_path / "logs")).model_copy(
        update={
            "allowed_writable_directories": [str(tmp_path)],
            "allowed_project_directories": [str(tmp_path)],
        }
    )
    executor = Executor(settings)
    await executor.run(["git", "init", str(root)])
    (root / "file.txt").write_text("hello")
    marker = tmp_path / "filter-executed"
    await executor.run(["git", "-C", str(root), "config", "filter.evil.clean", f"touch {marker}"])
    (root / ".gitattributes").write_text("*.txt filter=evil\n")
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(
            "git_add", {"path": str(root), "files": ["file.txt"], "confirmed": True}
        )
        assert not result.structured_content["success"]
        assert not marker.exists()
        (root / ".git" / "escape").symlink_to("/tmp")
        result = await client.call_tool("git_status", {"path": str(root)})
        assert not result.structured_content["success"]
