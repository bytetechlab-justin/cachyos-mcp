from typing import Any
from pathlib import Path
from pydantic import StrictBool
from ..security import confirm, identifier, service, Denied, text
from .kde import program, unit_quote


def register(r):
    @r.tool('systemd', 2)
    def create_systemd_user_service(name: str, executable: str, arguments: list[str], confirmed: StrictBool, description: str = 'CachyOS MCP managed application') -> dict[str, Any]:
        """Create a new cachyos-mcp-NAME.service; does not enable or start it."""
        confirm(confirmed)
        identifier(name)
        text(description)
        argv = program(r, executable, arguments)
        unit = 'cachyos-mcp-' + name + '.service'
        # ':' disables systemd environment expansion; %% escapes specifiers.
        content = '[Unit]\nDescription=' + description.replace('%', '%%') + '\n\n[Service]\nType=exec\nExecStart=:' + ' '.join(unit_quote(a) for a in argv) + '\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n'
        result = r.paths.write(str(Path.home() / '.config/systemd/user' / unit), content)
        return result | {'unit': unit, 'enabled': False, 'started': False}

    def action_tool(action):
        async def operation(name: str, confirmed: StrictBool) -> dict[str, Any]:
            confirm(confirmed)
            unit = service(name)
            if not unit.startswith('cachyos-mcp-'):
                raise Denied('Only cachyos-mcp-* user services may be controlled')
            # Verify a private, regular unit file before giving systemctl a unit name.
            r.paths.read(str(Path.home() / '.config/systemd/user' / unit))
            reload = await r.run(['systemctl', '--user', 'daemon-reload'])
            if not reload['success']:
                return reload
            return await r.run(['systemctl', '--user', action, '--', unit])
        operation.__name__ = action + '_systemd_user_service'
        operation.__doc__ = f'{action.capitalize()} an approved cachyos-mcp-* user service after confirmation.'
        r.tool('systemd', 2)(operation)
    for action in ('enable', 'disable', 'start', 'stop', 'restart'):
        action_tool(action)
