from typing import Any

from pydantic import StrictBool

from ..security import Denied, confirm, package, service


def register(r):
    def permitted(confirmed):
        confirm(confirmed)
        if not r.settings.privileged_enabled:
            raise Denied(
                "Privileged tools are disabled. The user must manually enable privileged_enabled in config/settings.toml and restart the client."
            )

    async def sudo(argv):
        result = await r.run(["/usr/bin/sudo", "-n", "--", *argv])
        if not result["success"] and any(
            s in result["stderr"].lower() for s in ("password", "terminal", "tty", "authentication")
        ):
            result["error"] = "authentication_required"
            result["hint"] = (
                "Authenticate in your host terminal. If sudo policy does not permit noninteractive cached authentication, run the displayed command there. This server never requests a password or changes sudo policy."
            )
        return result

    @r.tool("privileged", 3)
    async def install_package(name: str, confirmed: StrictBool) -> dict[str, Any]:
        """Install one administrator-allowlisted official repository package and its dependencies; requires enabled policy, explicit approval, and sudo authentication."""
        permitted(confirmed)
        name = package(name)
        if name not in r.settings.allowed_packages:
            raise Denied("Package is not in the administrator allowlist")
        return await sudo(
            ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--noprogressbar", "--", name]
        )

    @r.tool("privileged", 3)
    async def remove_package(name: str, confirmed: StrictBool) -> dict[str, Any]:
        """Remove one allowlisted package without cascading or recursive dependency removal."""
        permitted(confirmed)
        name = package(name)
        if name not in r.settings.allowed_packages:
            raise Denied("Package is not in the administrator allowlist")
        return await sudo(["/usr/bin/pacman", "-R", "--noconfirm", "--noprogressbar", "--", name])

    def action_tool(action):
        async def operation(name: str, confirmed: StrictBool) -> dict[str, Any]:
            permitted(confirmed)
            unit = service(name)
            if unit not in r.settings.allowed_services:
                raise Denied("Service is not in the administrator allowlist")
            return await sudo(["/usr/bin/systemctl", action, "--", unit])

        operation.__name__ = action + "_service"
        operation.__doc__ = f"{action.capitalize()} one administrator-allowlisted system service with enabled policy, confirmation, and authenticated sudo."
        r.tool("privileged", 3)(operation)

    for action in ("enable", "disable", "start", "stop", "restart"):
        action_tool(action)
