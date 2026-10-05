from typing import Any

from ..security import Denied
from .common import json_command


def register(r):
    @r.tool("network")
    async def get_network_interfaces() -> dict[str, Any]:
        """Interfaces, addresses, and link states as ip JSON."""
        return await json_command(r, ["ip", "-j", "address", "show"])

    @r.tool("network")
    async def get_network_info() -> dict[str, Any]:
        """Host routing table as JSON."""
        return await json_command(r, ["ip", "-j", "route", "show"])

    @r.tool("network")
    async def get_listening_ports(port: int | None = None) -> dict[str, Any]:
        """TCP/UDP listeners and visible owning processes, optionally filtered by port."""
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise Denied("Invalid port")
        argv = ["ss", "-H", "-lntup"]
        if port is not None:
            argv += ["sport", "=", ":" + str(port)]
        result = await r.run(argv)
        if result["success"]:
            rows = []
            for line in result["stdout"].splitlines():
                fields = line.split(None, 6)
                if len(fields) >= 6:
                    rows.append(
                        {
                            "protocol": fields[0],
                            "state": fields[1],
                            "recv_queue": fields[2],
                            "send_queue": fields[3],
                            "local": fields[4],
                            "peer": fields[5],
                            "process": fields[6] if len(fields) > 6 else None,
                        }
                    )
            result["data"] = rows
        return result
