from pathlib import Path
from mcp import Client
from cachyos_mcp.config import Settings
from cachyos_mcp.server import create_server
from cachyos_mcp.tools.kde import desktop_quote, unit_quote

async def test_widget_and_git(tmp_path):
    settings = Settings(log_directory=str(tmp_path / 'logs')).model_copy(update={'allowed_writable_directories': [str(tmp_path)], 'allowed_project_directories': [str(tmp_path)]})
    async with Client(create_server(settings)) as client:
        root = tmp_path / 'widget'
        result = await client.call_tool('create_plasma_widget_project', {'path': str(root), 'name': 'thermal', 'confirmed': True})
        assert result.structured_content['success']
        assert (root / 'contents/ui/main.qml').exists()
        result = await client.call_tool('git_init', {'path': str(root), 'confirmed': True})
        assert result.structured_content['success']
        result = await client.call_tool('git_status', {'path': str(root)})
        assert result.structured_content['success']
        result = await client.call_tool('git_add', {'path': str(root), 'files': ['metadata.json'], 'confirmed': True})
        assert result.structured_content['success']
        result = await client.call_tool('git_add', {'path': str(root), 'files': ['../escape'], 'confirmed': True})
        assert not result.structured_content['success']

async def test_service_name_and_desktop_injection(tmp_path):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        result = await client.call_tool('create_desktop_entry', {'name': 'evil\nExec=sh', 'executable': '/usr/bin/true', 'arguments': [], 'confirmed': True})
        assert not result.structured_content['success']
        result = await client.call_tool('restart_systemd_user_service', {'name': 'dbus', 'confirmed': True})
        assert not result.structured_content['success']
        result = await client.call_tool('create_systemd_user_service', {'name': 'x', 'executable': '/usr/bin/true', 'arguments': ['hello\nExecStart=/bin/sh'], 'confirmed': True})
        assert not result.structured_content['success']

def test_config_quotes():
    assert '%%' in desktop_quote('%f')
    assert '\\\\$' in desktop_quote('$HOME')
    assert unit_quote('%h') == '"%%h"'
