from typing import Any
import json
from .common import limit as valid_limit
from ..security import service, Denied


def register(r):
    async def read(unit=None, lines=100, boot=0, priority=None, user=False):
        valid_limit(lines)
        if type(boot) is not int or not -20 <= boot <= 0:
            raise Denied('Boot must be 0 (current) or a negative index down to -20')
        argv = ['journalctl', '--no-pager', '--output=json', '-n', str(lines), '-b', str(boot)]
        if user:
            argv.append('--user')
        if unit:
            argv += ['-u', service(unit)]
        if priority is not None:
            if type(priority) is not int or not 0 <= priority <= 7:
                raise Denied('Priority must be 0 through 7')
            argv += ['-p', str(priority)]
        result = await r.run(argv)
        if result['success']:
            fields = {'__REALTIME_TIMESTAMP', 'MESSAGE', 'PRIORITY', '_SYSTEMD_UNIT', '_SYSTEMD_USER_UNIT', '_COMM'}
            result['data'] = [{k: v for k, v in json.loads(line).items() if k in fields} for line in result['stdout'].splitlines()]
        return result

    @r.tool('journal')
    async def read_journal(unit: str | None = None, limit: int = 100, boot: int = 0, priority: int | None = None, user: bool = False) -> dict[str, Any]:
        """Bounded journal entries. Logs may contain sensitive application messages; review sharing."""
        return await read(unit, limit, boot, priority, user)

    @r.tool('journal')
    async def get_boot_errors(limit: int = 100, boot: int = 0) -> dict[str, Any]:
        """Errors and more severe journal messages for a boot."""
        return await read(lines=limit, boot=boot, priority=3)

    @r.tool('journal')
    async def get_boot_time() -> dict[str, Any]:
        """Boot timing summary and units delaying startup."""
        result = await r.run(['systemd-analyze', 'time'])
        blame = await r.run(['systemd-analyze', 'blame', '--no-pager'])
        result['data'] = {'timing': result['stdout'], 'blame': blame}
        return result
