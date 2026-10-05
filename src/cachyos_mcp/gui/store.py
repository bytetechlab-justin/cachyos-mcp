"""Validated, comment-preserving policy saves with conflict detection and bounded backups."""

import fcntl
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import tomlkit

from ..config import Settings
from ..security import Paths

MAX_POLICY_BYTES = 1048576
BACKUP_COUNT = 5


class ConflictError(ValueError):
    """The loaded policy no longer matches the disk contents."""


@dataclass
class Snapshot:
    path: Path
    raw: bytes
    settings: Settings


def _read(fd: int, name: str) -> bytes:
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(source, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Choose a regular policy file without symlinks or hardlinks")
        raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise ValueError("Policy exceeds the 1 MiB size limit")
        return raw


def read_snapshot(path: Path) -> Snapshot:
    path = path.expanduser().absolute()
    paths = Paths(Settings())
    with paths.parent(path) as (fd, name):
        raw = _read(fd, name)
    settings = Settings.model_validate(tomlkit.parse(raw.decode("utf-8")).unwrap())
    settings._policy_path = path
    return Snapshot(path, raw, settings)


def render(snapshot: Snapshot, settings: Settings) -> bytes:
    document = tomlkit.parse(snapshot.raw.decode("utf-8"))
    for key, value in settings.model_dump().items():
        if key not in document or document[key] != value:
            document[key] = value
    raw = tomlkit.dumps(document).encode("utf-8")
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("Policy exceeds the 1 MiB size limit")
    Settings.model_validate(tomlkit.parse(raw.decode("utf-8")).unwrap())
    return raw


def _write(fd: int, name: str, raw: bytes):
    destination = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
    )
    with os.fdopen(destination, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save(snapshot: Snapshot, settings: Settings) -> tuple[Snapshot, Path]:
    """Save only against the exact loaded file; never clobber external edits."""
    # Revalidate even when called without the GUI.
    settings = Settings.model_validate(settings.model_dump())
    raw = render(snapshot, settings)
    paths = Paths(Settings())
    with paths.parent(snapshot.path) as (fd, name):
        lock = os.open(".settings.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if _read(fd, name) != snapshot.raw:
                raise ConflictError(
                    "Settings changed on disk. Reload them before saving your changes."
                )
            try:
                os.mkdir(".settings-backups", 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            backup_fd = os.open(
                ".settings-backups", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            try:
                os.fchmod(backup_fd, 0o700)
                backup_name = (
                    datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex + ".toml"
                )
                _write(backup_fd, backup_name, snapshot.raw)
                os.fsync(backup_fd)
                # Remove only our regular, private backup filenames; never follow links.
                import re

                backups = sorted(
                    p
                    for p in os.listdir(backup_fd)
                    if re.fullmatch(r"\d{8}T\d{6}\.\d{6}Z-[a-f0-9]{32}\.toml", p)
                )
                for old in backups[:-BACKUP_COUNT]:
                    info = os.stat(old, dir_fd=backup_fd, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        os.unlink(old, dir_fd=backup_fd)
            finally:
                os.close(backup_fd)
            temp = ".settings-" + uuid.uuid4().hex + ".tmp"
            try:
                _write(fd, temp, raw)
                # Catch edits made by an editor that does not participate in our lock.
                if _read(fd, name) != snapshot.raw:
                    raise ConflictError("Settings changed during save. Reload before trying again.")
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(lock)
    settings._policy_path = snapshot.path
    return Snapshot(
        snapshot.path, raw, settings
    ), snapshot.path.parent / ".settings-backups" / backup_name


def backups(snapshot: Snapshot) -> list[Path]:
    directory = snapshot.path.parent / ".settings-backups"
    if not directory.exists():
        return []
    if directory.is_symlink():
        raise ValueError("Backup directory must not be a symlink")
    return sorted(directory.glob("*.toml"), reverse=True)
