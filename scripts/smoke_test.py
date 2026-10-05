#!/usr/bin/env python3
"""Read-only end-to-end probe of the installed stdio server. No mutation tools are called."""

import asyncio
import json
from pathlib import Path

from mcp import Client, StdioServerParameters

PROJECT = Path(__file__).resolve().parents[1]


async def main():
    calls = [
        ("get_system_info", {}),
        ("get_kernel_info", {}),
        ("get_cpu_info", {}),
        ("get_memory_info", {}),
        ("get_disk_usage", {}),
        ("get_mounts", {}),
        ("get_gpu_info", {}),
        ("get_nvidia_status", {}),
        ("get_temperatures", {}),
        ("get_network_info", {}),
        ("get_network_interfaces", {}),
        ("get_listening_ports", {"port": 8080}),
        ("list_processes", {"limit": 5}),
        ("find_process", {"name": "plasmashell"}),
        ("list_usb_devices", {}),
        ("list_pci_devices", {}),
        ("list_installed_packages", {"limit": 5}),
        ("search_packages", {"query": "blender", "limit": 3}),
        ("get_package_info", {"name": "pacman"}),
        ("get_service_status", {"name": "bluetooth"}),
        ("list_failed_services", {}),
        ("list_running_services", {}),
        ("read_journal", {"unit": "bluetooth", "limit": 5}),
        ("get_boot_errors", {"limit": 5}),
        ("get_boot_time", {}),
        ("get_user_info", {}),
        ("get_environment_info", {}),
        ("get_kde_info", {}),
        ("get_plasma_version", {}),
        ("inspect_plasma_configuration", {}),
        ("inspect_path", {"path": str(Path.home() / ".config/kdeglobals")}),
    ]
    summary = {"tools": 0, "checks": []}
    async with Client(
        StdioServerParameters(command=str(PROJECT / "scripts/launch.sh")), mode="legacy"
    ) as client:
        tools = await client.list_tools()
        summary["tools"] = len(tools.tools)
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            payload = result.structured_content or {}
            check = {"tool": name, "success": payload.get("success", False) and not result.is_error}
            if not check["success"]:
                check["error"] = payload.get("error", "MCP error")
            summary["checks"].append(check)
        result = await client.call_tool("get_listening_ports", {"port": "bad"})
        summary["legacy_invalid_args_rejected"] = result.is_error
    print(json.dumps(summary, indent=2))
    if (
        not all(c["success"] for c in summary["checks"])
        or not summary["legacy_invalid_args_rejected"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
