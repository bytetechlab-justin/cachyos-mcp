from typing import Any
import os
from pathlib import Path
from pydantic import StrictBool
from ..security import confirm, text, Denied

GIT = ['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'core.pager=cat']


def register(r):
    async def git(path, args, repository=True):
        root = r.paths.checked(path, write=True, project=True)
        with r.paths.parent(root) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            if repository:
                repo_fd = os.open('.git', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(repo_fd)
            return await r.executor.run([*GIT, *args], cwd=str(root), cwd_fd=fd)
        finally:
            os.close(fd)

    @r.tool('development')
    async def git_status(path: str) -> dict[str, Any]:
        """Git status inside an approved project, with hooks and fsmonitor disabled."""
        return await git(path, ['status', '--porcelain=v1', '--untracked-files=normal'])

    @r.tool('development')
    async def git_diff(path: str) -> dict[str, Any]:
        """Working tree diff with external diff programs and text conversion disabled."""
        return await git(path, ['diff', '--no-ext-diff', '--no-textconv', '--'])

    @r.tool('development')
    async def git_log(path: str, limit: int = 20) -> dict[str, Any]:
        """Recent commits inside an approved project."""
        from .common import limit as valid_limit
        valid_limit(limit, 100)
        return await git(path, ['log', '-' + str(limit), '--format=%h %s'])

    @r.tool('development', 2)
    async def git_init(path: str, confirmed: StrictBool) -> dict[str, Any]:
        """Initialize Git in an existing approved project directory."""
        confirm(confirmed)
        return await git(path, ['init'], repository=False)

    @r.tool('development', 2)
    async def git_add(path: str, files: list[str], confirmed: StrictBool) -> dict[str, Any]:
        """Stage explicitly named regular project files; no directories, traversal, or pathspec magic."""
        confirm(confirmed)
        root = r.paths.checked(path, write=True, project=True)
        if not 1 <= len(files) <= 100:
            raise Denied('Provide 1 to 100 file names')
        for name in files:
            text(name, 4096)
            if Path(name).is_absolute() or '..' in Path(name).parts or name.startswith(('-', ':')):
                raise Denied('Unsafe Git file path')
            candidate = r.paths.checked(str(root / name), write=True, project=True)
            with r.paths.parent(candidate) as (fd, leaf):
                import stat
                if not stat.S_ISREG(os.stat(leaf, dir_fd=fd, follow_symlinks=False).st_mode):
                    raise Denied('Only regular files can be staged')
        return await git(path, ['--literal-pathspecs', 'add', '--', *files])

    @r.tool('development', 2)
    async def git_commit(path: str, message: str, confirmed: StrictBool) -> dict[str, Any]:
        """Commit already staged changes; hooks/signing are disabled and user identity must exist."""
        confirm(confirmed)
        text(message, 2048)
        return await git(path, ['commit', '-m', message])
