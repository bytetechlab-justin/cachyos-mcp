from typing import Any
import csv
import io
from .common import json_command


def register(r):
    @r.tool('hardware')
    async def get_gpu_info() -> dict[str, Any]:
        """PCI hardware and driver bindings (includes all graphics devices)."""
        return await r.run(['lspci', '-nnk'])

    @r.tool('hardware')
    async def get_nvidia_status() -> dict[str, Any]:
        """NVIDIA GPUs, driver, temperature, utilization, and VRAM usage."""
        keys = ['index', 'name', 'driver_version', 'temperature.gpu', 'utilization.gpu', 'memory.total', 'memory.used']
        result = await r.run(['nvidia-smi', '--query-gpu=' + ','.join(keys), '--format=csv,noheader,nounits'])
        if result['success']:
            result['data'] = {'gpus': [dict(zip(keys, [x.strip() for x in row], strict=True)) for row in csv.reader(io.StringIO(result['stdout']))], 'units': {'temperature.gpu': 'C', 'utilization.gpu': '%', 'memory.total': 'MiB', 'memory.used': 'MiB'}}
        return result

    @r.tool('hardware')
    async def get_temperatures() -> dict[str, Any]:
        """lm-sensors JSON readings; combine with get_nvidia_status for NVIDIA temperature."""
        return await json_command(r, ['sensors', '-j'])

    @r.tool('hardware')
    async def list_usb_devices() -> dict[str, Any]:
        """Enumerate USB devices."""
        return await r.run(['lsusb'])

    @r.tool('hardware')
    async def list_pci_devices() -> dict[str, Any]:
        """Enumerate PCI devices and bound kernel drivers."""
        return await r.run(['lspci', '-nnk'])
