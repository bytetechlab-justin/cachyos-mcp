"""Argument validation and descriptor-relative, no-symlink filesystem access."""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import stat
from .config import PROJECT

class Denied(ValueError):
    pass


def text(value: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise Denied('Invalid text argument')
    return value


def package(value: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@._+\-]{0,127}', value):
        raise Denied('Invalid package name; options and shell syntax are forbidden')
    return value


def service(value: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.@\-]{0,127}', value):
        raise Denied('Invalid service name')
    if '.' not in value:
        value += '.service'
    if not value.endswith('.service'):
        raise Denied('Only .service units are supported')
    return value


def identifier(value: str) -> str:
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_\-]{0,63}', value):
        raise Denied('Invalid identifier')
    return value


def confirm(value: bool):
    if value is not True:
        raise Denied('Explicit confirmed=true required after user approves this change')

SECRET_PARTS = {'.ssh', '.gnupg', '.aws', '.codex', '.claude', '.git', '.venv',
                'credentials', 'secrets', 'keyrings', 'kwalletd', 'kwalletrc',
                'environment.d', 'sudoers', 'sudoers.d', 'autostart', 'fish',
                '.bashrc', '.profile', '.zshrc', '.mcp.json', 'settings.json'}

class Paths:
    def __init__(self, settings):
        self.settings = settings

    def checked(self, value: str, write=False, project=False) -> Path:
        text(value, 4096)
        p = Path(value).expanduser()
        if not p.is_absolute() or '..' in p.parts:
            raise Denied('Use an absolute path without traversal')
        for part in p.parts:
            lower = part.lower()
            if lower in SECRET_PARTS or lower.startswith('.env') or any(x in lower for x in ('token', 'password', 'secret', 'credential', 'private_key')) or lower.endswith(('.pem', '.key')):
                raise Denied('Sensitive or policy path is blocked')
        # Never permit tools to rewrite their own code, policy, environment, logs, or launcher.
        if p.is_relative_to(PROJECT):
            raise Denied('Server project is protected from MCP filesystem tools')
        if not write:
            if not any(p.is_relative_to(Path(root)) for root in (str(Path.home()), '/etc', '/var/log', '/usr/share')):
                raise Denied('Read location is outside approved diagnostic roots')
        else:
            roots = self.settings.allowed_project_directories if project else self.settings.allowed_writable_directories
            if not any(p.is_relative_to(Path(root).expanduser()) and p != Path(root).expanduser() for root in roots):
                raise Denied('Location is outside writable roots or is a root itself')
        return p

    @contextmanager
    def parent(self, p: Path, create=False):
        """Anchor all traversal to directory FDs: symlink swaps cannot redirect writes."""
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in p.parts[1:-1]:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            yield fd, p.name
        finally:
            os.close(fd)

    def read(self, value: str) -> str:
        p = self.checked(value)
        with self.parent(p) as (fd, name):
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file_fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise Denied('Only regular, single-link files may be read')
                data = stream.read(self.settings.max_file_size + 1)
                if len(data) > self.settings.max_file_size:
                    raise Denied('File exceeds configured read limit')
                return data.decode('utf-8')

    def write(self, value: str, content: str, replace=False, executable=False):
        p = self.checked(value, write=True)
        data = content.encode('utf-8')
        if len(data) > self.settings.max_file_size:
            raise Denied('File exceeds configured write limit')
        with self.parent(p, create=True) as (fd, name):
            if not replace:
                new = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700 if executable else 0o600, dir_fd=fd)
                with os.fdopen(new, 'wb') as stream:
                    stream.write(data)
                return {'path': str(p), 'bytes': len(data)}
            # Existing files are read without following links; backup never overwrites.
            old = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(old, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > self.settings.max_file_size:
                    raise Denied('Unsafe file type, hardlink, or size')
                previous = stream.read(self.settings.max_file_size + 1)
                if len(previous) > self.settings.max_file_size:
                    raise Denied('File grew beyond limit')
            import uuid
            suffix = uuid.uuid4().hex
            backup = name + '.backup-' + suffix
            bfd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(bfd, 'wb') as stream:
                stream.write(previous)
            temp = name + '.tmp-' + suffix
            tfd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, info.st_mode & 0o700, dir_fd=fd)
            try:
                with os.fdopen(tfd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass
            return {'path': str(p), 'bytes': len(data), 'backup': str(p.with_name(backup))}

    def mkdir(self, value: str):
        p = self.checked(value, write=True)
        with self.parent(p, create=True) as (fd, name):
            os.mkdir(name, 0o700, dir_fd=fd)
        return {'path': str(p)}
