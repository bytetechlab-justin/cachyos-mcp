from typing import Any
from ..security import package, text
from .common import limit as valid_limit


def register(r):
    @r.tool('packages')
    async def list_installed_packages(query: str | None = None, limit: int = 200) -> dict[str, Any]:
        """Installed package names and versions; optional literal substring filter."""
        valid_limit(limit, 5000)
        if query is not None:
            text(query, 128)
        result = await r.run(['pacman', '-Q'])
        if result['success']:
            rows = [line.split(None, 1) for line in result['stdout'].splitlines()]
            result['data'] = [{'name': name, 'version': version} for name, version in rows if query is None or query.lower() in name.lower()][:limit]
        return result

    @r.tool('packages')
    async def search_packages(query: str, limit: int = 100) -> dict[str, Any]:
        """Search configured official repositories without refreshing databases."""
        package(query)
        valid_limit(limit)
        result = await r.run(['pacman', '-Ss', '--', query])
        if result['success']:
            result['data'] = result['stdout'].splitlines()[:limit*2]
        return result

    @r.tool('packages')
    async def get_package_info(name: str, installed: bool = True) -> dict[str, Any]:
        """Installed (-Qi) or repository (-Si) package metadata."""
        return await r.run(['pacman', '-Qi' if installed else '-Si', '--', package(name)])
