from typing import Any

from ..security import service
from .common import json_command


def register(r):
    @r.tool("systemd")
    async def get_service_status(name: str, user: bool = False) -> dict[str, Any]:
        """Selected service properties, excluding environment and command-line secrets."""
        result = await r.run(
            [
                "systemctl",
                *(["--user"] if user else []),
                "show",
                "--no-pager",
                "--property=Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,Result",
                "--",
                service(name),
            ]
        )
        if result["success"]:
            result["data"] = dict(
                line.split("=", 1) for line in result["stdout"].splitlines() if "=" in line
            )
        return result

    @r.tool("systemd")
    async def list_failed_services(user: bool = False) -> dict[str, Any]:
        """Failed system or user services as systemctl JSON."""
        return await json_command(
            r,
            [
                "systemctl",
                *(["--user"] if user else []),
                "list-units",
                "--type=service",
                "--state=failed",
                "--all",
                "--no-pager",
                "--output=json",
            ],
        )

    @r.tool("systemd")
    async def list_running_services(user: bool = False) -> dict[str, Any]:
        """Running system or user services as systemctl JSON."""
        return await json_command(
            r,
            [
                "systemctl",
                *(["--user"] if user else []),
                "list-units",
                "--type=service",
                "--state=running",
                "--no-pager",
                "--output=json",
            ],
        )
