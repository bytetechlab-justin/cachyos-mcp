import sys

import pytest

from cachyos_mcp.config import Settings
from cachyos_mcp.executor import Executor
from cachyos_mcp.security import Denied, package, service


@pytest.mark.parametrize("value", [";id", "foo$(id)", "foo`id`", "-S", "a b", "a\nb", "../foo", ""])
def test_argument_injection(value):
    with pytest.raises(Denied):
        package(value)
    with pytest.raises(Denied):
        service(value)


async def test_no_shell(tmp_path):
    target = tmp_path / "injected"
    result = await Executor(Settings()).run(
        [sys.executable, "-c", "import sys;print(sys.argv[1])", f"$(touch {target})"]
    )
    assert result["success"]
    assert not target.exists()


async def test_timeout():
    result = await Executor(Settings(max_command_timeout=1)).run(
        [sys.executable, "-c", "import time;time.sleep(10)"]
    )
    assert result["error"] == "timeout"
    assert result["duration_ms"] < 2500


async def test_output_limit():
    result = await Executor(Settings(max_output_size=1024)).run(
        [sys.executable, "-c", 'print("x"*100000)']
    )
    assert result["truncated"] and result["error"] == "output_limit"
    assert len(result["stdout"].encode()) <= 1024


async def test_missing_command():
    result = await Executor(Settings()).run(["missing-cachyos-command"])
    assert result["error"] == "missing_executable"


def test_config_rejects_unknown():
    with pytest.raises(ValueError):
        Settings.model_validate({"privileged_enable": True})
