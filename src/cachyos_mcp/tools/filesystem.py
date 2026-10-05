import os
import stat
from typing import Any

from pydantic import StrictBool

from ..security import Denied, confirm


def register(r):
    @r.tool("filesystem")
    def inspect_path(path: str) -> dict[str, Any]:
        """Inspect metadata of an approved diagnostic path without following symlinks."""
        p = r.paths.checked(path)
        with r.paths.parent(p) as (fd, name):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        return {
            "path": str(p),
            "size": info.st_size,
            "mode": oct(stat.S_IMODE(info.st_mode)),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "is_directory": stat.S_ISDIR(info.st_mode),
            "is_symlink": stat.S_ISLNK(info.st_mode),
            "mtime": info.st_mtime,
        }

    @r.tool("filesystem")
    def read_file(path: str) -> dict[str, Any]:
        """Read a bounded, UTF-8, non-sensitive regular file in diagnostic roots."""
        return {"path": path, "content": r.paths.read(path)}

    @r.tool("filesystem", 2)
    def create_file(path: str, content: str, confirmed: StrictBool) -> dict[str, Any]:
        """Create a new file inside writable roots after user approval; never overwrite."""
        confirm(confirmed)
        return r.paths.write(path, content)

    @r.tool("filesystem", 2)
    def edit_file(path: str, content: str, confirmed: StrictBool) -> dict[str, Any]:
        """Replace approved file contents atomically, keeping a private backup first."""
        confirm(confirmed)
        return r.paths.write(path, content, replace=True)

    @r.tool("filesystem", 2)
    def create_directory(path: str, confirmed: StrictBool) -> dict[str, Any]:
        """Create a new private directory inside writable roots."""
        confirm(confirmed)
        return r.paths.mkdir(path)

    @r.tool("filesystem", 2)
    def create_symlink(path: str, target: str, confirmed: StrictBool) -> dict[str, Any]:
        """Create a new symlink to an existing approved writable target. File tools never follow links."""
        confirm(confirmed)
        p = r.paths.checked(path, write=True)
        t = r.paths.checked(target, write=True)
        with r.paths.parent(t) as (fd, name):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise Denied("Symlink target must be a regular file or directory")
        with r.paths.parent(p, create=True) as (fd, name):
            os.symlink(str(t), name, dir_fd=fd)
        return {"path": str(p), "target": str(t)}

    @r.tool("filesystem", 2)
    def create_script(path: str, content: str, confirmed: StrictBool) -> dict[str, Any]:
        """Create a private executable script; this tool does not execute it."""
        confirm(confirmed)
        if not content.startswith("#!"):
            raise Denied("Scripts require a shebang")
        return r.paths.write(path, content, executable=True)
