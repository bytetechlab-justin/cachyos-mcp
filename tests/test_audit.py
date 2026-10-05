import json

from cachyos_mcp.config import Settings
from cachyos_mcp.logging_config import Audit


def test_rotation(tmp_path):
    settings = Settings(log_directory=str(tmp_path), log_max_bytes=1024, log_backups=2)
    audit = Audit(settings)
    for i in range(100):
        audit.record(
            tool="example", permission_level=1, event="finish", success=True, duration_ms=i
        )
    logs = list(tmp_path.glob("audit.jsonl*"))
    assert len(logs) == 3
    for file in logs:
        assert file.stat().st_size <= 1024
        assert file.stat().st_mode & 0o077 == 0
        for line in file.read_text().splitlines():
            assert "timestamp" in json.loads(line)


def test_arbitrary_command_arguments_are_redacted():
    from cachyos_mcp.runtime import Runtime

    result = Runtime.safe_command(["git", "--secret-token-value", "-m", "private-key-material"])
    assert result == ["git", "[argument]", "[argument]", "[argument]"]
