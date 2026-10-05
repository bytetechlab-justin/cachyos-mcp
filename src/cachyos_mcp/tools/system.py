import os
import platform
import pwd
import shutil
from pathlib import Path


def register(r):
    @r.tool('system')
    def get_system_info() -> dict:
        """Host OS release, architecture, hostname, and Python version."""
        return {'os': platform.freedesktop_os_release(), 'hostname': platform.node(), 'architecture': platform.machine(), 'python': platform.python_version()}

    @r.tool('system')
    def get_kernel_info() -> dict:
        """Kernel name, version, and release."""
        u = platform.uname()
        return {'system': u.system, 'release': u.release, 'version': u.version, 'machine': u.machine}

    @r.tool('system')
    async def get_cpu_info() -> dict:
        """CPU topology and features, using lscpu JSON."""
        result = await r.run(['lscpu', '--json'])
        if result['success']:
            import json
            result['data'] = json.loads(result['stdout'])
        return result

    @r.tool('system')
    def get_memory_info() -> dict:
        """RAM and swap amounts in bytes, from host /proc/meminfo."""
        fields = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            fields[key] = int(value.split()[0]) * 1024
        return {'total': fields['MemTotal'], 'available': fields['MemAvailable'], 'used': fields['MemTotal']-fields['MemAvailable'], 'swap_total': fields['SwapTotal'], 'swap_used': fields['SwapTotal']-fields['SwapFree'], 'unit': 'bytes'}

    @r.tool('system')
    def get_disk_usage() -> dict:
        """Usage of the root and home filesystems in bytes."""
        return {'filesystems': [{'path': p, **dict(zip(('total', 'used', 'free'), shutil.disk_usage(p), strict=True))} for p in ('/', str(Path.home()))]}

    @r.tool('system')
    async def get_mounts() -> dict:
        """Host mounted filesystems as findmnt JSON."""
        import json
        result = await r.run(['findmnt', '--json', '--output', 'TARGET,SOURCE,FSTYPE,OPTIONS'])
        if result['success']:
            result['data'] = json.loads(result['stdout'])
        return result

    @r.tool('system')
    def get_user_info() -> dict:
        """Current unprivileged identity and groups."""
        account = pwd.getpwuid(os.getuid())
        return {'name': account.pw_name, 'uid': os.getuid(), 'gid': os.getgid(), 'groups': os.getgroups(), 'home': account.pw_dir, 'shell': account.pw_shell}

    @r.tool('system')
    def get_environment_info() -> dict:
        """Only desktop/session metadata; never dump the full environment."""
        return {k: os.environ.get(k) for k in ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE', 'DESKTOP_SESSION', 'LANG')}
