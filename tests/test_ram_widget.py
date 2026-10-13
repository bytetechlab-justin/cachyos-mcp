import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "plasma/org.cachyos.ramgauge/contents/code/reclaim.sh"


def run(cgroup: Path, meminfo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "RAMGAUGE_CGROUP": str(cgroup), "RAMGAUGE_MEMINFO": str(meminfo)},
        capture_output=True, text=True, timeout=20,
    )


def test_reclaims_only_idle_pages_in_steps(tmp_path):
    (tmp_path / "memory.stat").write_text(
        "anon 999999999999\ninactive_anon 314572800\nactive_anon 999999999999\ninactive_file 1048576\n"
    )
    (tmp_path / "memory.reclaim").write_text("")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 32000000 kB\nMemAvailable: 1000 kB\n")
    result = run(tmp_path, meminfo)
    assert result.returncode == 0
    assert result.stdout.strip() == "freed_kb=0"
    # 300 MiB + 1 MiB idle: one full 256 MiB step, then the 45 MiB remainder.
    assert (tmp_path / "memory.reclaim").read_text().strip() == "46080K"


def test_reports_unsupported_without_delegated_cgroup(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable: 1000 kB\n")
    result = run(tmp_path / "missing", meminfo)
    assert result.returncode == 1
    assert result.stdout.strip() == "error=unsupported"
