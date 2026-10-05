from typing import Any
from pathlib import Path
from pydantic import StrictBool
import configparser
import json
import os
from ..security import confirm, identifier, text, Denied

PLASMA_CONFIGS = {'kdeglobals', 'plasmarc', 'plasmashellrc', 'kwinrc', 'plasma-org.kde.plasma.desktop-appletsrc'}


def program(r, executable, args):
    text(executable, 4096)
    p = Path(executable)
    if not p.is_absolute() or '..' in p.parts or not p.is_file() or not os.access(p, os.X_OK):
        raise Denied('Executable must be an existing absolute executable file')
    if p.parent != Path('/usr/bin'):
        r.paths.checked(executable, write=True, project=True)
        with r.paths.parent(p) as (fd, name):
            if os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode & 0o170000 != 0o100000:
                raise Denied('Project executable must be a regular file')
    if len(args) > 32:
        raise Denied('At most 32 program arguments')
    for arg in args:
        text(arg, 4096)
    return [executable, *args]


def desktop_quote(value):
    # Desktop Entry spec: reserved chars escaped inside double quotes, then backslashes
    # escaped again for the general string-value unescaping pass. No field-code expansion.
    value = value.replace('%', '%%')
    escaped = ''.join('\\' + c if c in ('\\', '"', '`', '$') else c for c in value)
    return '"' + escaped.replace('\\', '\\\\') + '"'


def unit_quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def register(r):
    @r.tool('kde')
    async def get_plasma_version() -> dict[str, Any]:
        """Installed Plasma version."""
        return await r.run(['plasmashell', '--version'])

    @r.tool('kde')
    async def get_kde_info() -> dict[str, Any]:
        """Plasma version and standard configuration/package paths."""
        result = await r.run(['plasmashell', '--version'])
        result['data'] = {'config_directory': str(Path.home() / '.config'), 'known_configs': sorted(PLASMA_CONFIGS), 'widgets_directory': str(Path.home() / '.local/share/plasma/plasmoids')}
        return result

    @r.tool('kde')
    def inspect_plasma_configuration(filename: str = 'kdeglobals') -> dict[str, Any]:
        """Inspect groups and setting names in known Plasma configuration, without changing it."""
        if filename not in PLASMA_CONFIGS:
            raise Denied('Unsupported Plasma config; choose one from get_kde_info')
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        parser.read_string(r.paths.read(str(Path.home() / '.config' / filename)))
        return {'file': filename, 'groups': {s: list(parser[s].keys()) for s in parser.sections()}}

    @r.tool('kde', 2)
    def create_desktop_entry(name: str, executable: str, arguments: list[str], confirmed: StrictBool, display_name: str = 'CachyOS Application') -> dict[str, Any]:
        """Create a new KDE application launcher after approving its executable and arguments."""
        confirm(confirmed)
        identifier(name)
        text(display_name)
        argv = program(r, executable, arguments)
        content = '[Desktop Entry]\nType=Application\nVersion=1.0\nName=' + display_name.replace('\\', '\\\\') + '\nExec=' + ' '.join(desktop_quote(a) for a in argv) + '\nTerminal=false\nCategories=Utility;\n'
        return r.paths.write(str(Path.home() / '.local/share/applications' / (name + '.desktop')), content)

    @r.tool('kde', 2)
    def create_plasma_widget_project(path: str, name: str, confirmed: StrictBool, cpu_sensor: str = 'cpu/all/averageTemperature', gpu_sensor: str = 'gpu/gpu0/temperature') -> dict[str, Any]:
        """Create a Plasma 6 CPU/GPU temperature widget project; does not install or alter the desktop."""
        confirm(confirmed)
        identifier(name)
        root = r.paths.checked(path, write=True, project=True)
        for sensor in (cpu_sensor, gpu_sensor):
            import re
            if not re.fullmatch(r'[a-zA-Z0-9_/-]{1,128}', sensor) or '..' in sensor:
                raise Denied('Invalid sensor ID')
        r.paths.mkdir(str(root))
        plugin_id = 'local.cachyos.' + name
        metadata = {'KPlugin': {'Id': plugin_id, 'Name': 'CPU and GPU Temperatures', 'Description': 'Live workstation temperature readings', 'Version': '1.0', 'License': 'MIT', 'Category': 'System Information', 'Icon': 'utilities-system-monitor'}, 'KPackageStructure': 'Plasma/Applet', 'X-Plasma-API-Minimum-Version': '6.0'}
        qml = '''import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.ksysguard.sensors as Sensors

PlasmoidItem {
    id: root
    Sensors.Sensor { id: cpu; sensorId: CPU_SENSOR }
    Sensors.Sensor { id: gpu; sensorId: GPU_SENSOR }
    fullRepresentation: ColumnLayout {
        PlasmaComponents.Label {
            text: "CPU: " + (cpu.status === Sensors.Sensor.Ready ? Number(cpu.value).toFixed(1) + " °C" : "Unavailable")
        }
        PlasmaComponents.Label {
            text: "GPU: " + (gpu.status === Sensors.Sensor.Ready ? Number(gpu.value).toFixed(1) + " °C" : "Unavailable")
        }
    }
}
'''.replace('CPU_SENSOR', json.dumps(cpu_sensor)).replace('GPU_SENSOR', json.dumps(gpu_sensor))
        r.paths.write(str(root / 'metadata.json'), json.dumps(metadata, indent=2) + '\n')
        r.paths.write(str(root / 'contents/ui/main.qml'), qml)
        r.paths.write(str(root / 'README.md'), '# Temperature widget\n\nInstall from a host terminal with `kpackagetool6 --type Plasma/Applet --install .`. Add it using Plasma’s Add Widgets menu. Sensor IDs vary by machine; adjust sensorId in contents/ui/main.qml using KDE System Monitor. Unavailable readings are displayed explicitly.\n')
        return {'path': str(root), 'plugin_id': plugin_id, 'files': ['metadata.json', 'contents/ui/main.qml', 'README.md'], 'installed': False}
