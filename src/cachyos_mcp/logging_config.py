"""Bounded JSON audit records. No content, environment, or command output is logged."""

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path


class Audit:
    def __init__(self, settings):
        self.settings = settings
        self.directory = Path(settings.log_directory).expanduser()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_uid != os.getuid():
            raise ValueError("Unsafe audit directory")
        os.chmod(self.directory, 0o700)

    def record(self, **fields):
        fields["timestamp"] = datetime.now(UTC).isoformat()
        data = (json.dumps(fields, ensure_ascii=True) + "\n").encode()
        path = self.directory / "audit.jsonl"
        lock = os.open(
            self.directory / ".audit.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.exists() and path.stat().st_size + len(data) > self.settings.log_max_bytes:
                for number in range(self.settings.log_backups, 0, -1):
                    source = path if number == 1 else path.with_suffix(f".jsonl.{number - 1}")
                    target = path.with_suffix(f".jsonl.{number}")
                    if source.exists():
                        os.replace(source, target)
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        finally:
            os.close(lock)
