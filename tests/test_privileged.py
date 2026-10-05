import pytest
from mcp import Client
from cachyos_mcp.config import Settings
from cachyos_mcp.server import create_server
from cachyos_mcp.executor import Executor

@pytest.mark.parametrize('name,args', [('install_package', {'name': 'blender'}), ('remove_package', {'name': 'blender'}), ('restart_service', {'name': 'bluetooth'})])
async def test_default_privilege_block(tmp_path, name, args, monkeypatch):
    async def forbidden(*a, **k):
        raise AssertionError('Privileged subprocess must not run')
    monkeypatch.setattr(Executor, 'run', forbidden)
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        result = await client.call_tool(name, args | {'confirmed': True})
        assert not result.structured_content['success']

async def test_allowlist_and_sudo_boundary(tmp_path, monkeypatch):
    calls = []
    async def fake(self, argv, **kwargs):
        calls.append(argv)
        return {'success': False, 'command': argv, 'exit_code': 1, 'stdout': '', 'stderr': 'sudo: a password is required', 'duration_ms': 1}
    monkeypatch.setattr(Executor, 'run', fake)
    async with Client(create_server(Settings(log_directory=str(tmp_path), privileged_enabled=True))) as client:
        for name, args in [('install_package', {'name': 'sudo'}), ('restart_service', {'name': 'sshd'}), ('install_package', {'name': 'blender;id'})]:
            result = await client.call_tool(name, args | {'confirmed': True})
            assert not result.structured_content['success']
        assert not calls
        result = await client.call_tool('install_package', {'name': 'blender', 'confirmed': True})
        assert result.structured_content['error'] == 'authentication_required'
        assert calls == [['/usr/bin/sudo', '-n', '--', '/usr/bin/pacman', '-S', '--needed', '--noconfirm', '--', 'blender']]
