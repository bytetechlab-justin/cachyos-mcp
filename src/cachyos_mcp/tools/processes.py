from pathlib import Path
from typing import Any

from ..security import Denied, text
from .common import limit as valid_limit


def register(r):
    async def processes():
        # comm deliberately omits command-line credentials and environment.
        result = await r.run(
            ["ps", "-eo", "pid=,ppid=,user=,pcpu=,pmem=,stat=,comm=", "--sort=-pcpu"]
        )
        if result["success"]:
            rows = []
            for line in result["stdout"].splitlines():
                fields = line.split(None, 6)
                if len(fields) == 7:
                    rows.append(
                        dict(
                            zip(
                                [
                                    "pid",
                                    "ppid",
                                    "user",
                                    "cpu_percent",
                                    "memory_percent",
                                    "state",
                                    "name",
                                ],
                                [
                                    int(fields[0]),
                                    int(fields[1]),
                                    fields[2],
                                    float(fields[3]),
                                    float(fields[4]),
                                    fields[5],
                                    fields[6],
                                ],
                                strict=True,
                            )
                        )
                    )
            result["data"] = rows
        return result

    @r.tool("processes")
    async def list_processes(limit: int = 100) -> dict[str, Any]:
        """Top processes by CPU; omit command lines that can contain secrets."""
        valid_limit(limit)
        result = await processes()
        if result["success"]:
            result["data"] = result["data"][:limit]
        return result

    @r.tool("processes")
    async def find_process(name: str, limit: int = 100) -> dict[str, Any]:
        """Find process names containing a literal case-insensitive substring."""
        text(name, 128)
        valid_limit(limit)
        result = await processes()
        if result["success"]:
            result["data"] = [p for p in result["data"] if name.lower() in p["name"].lower()][
                :limit
            ]
        return result

    @r.tool("processes")
    def get_process_details(pid: int) -> dict[str, Any]:
        """Selected /proc process status; no command line or environment secrets."""
        if type(pid) is not int or not 1 <= pid <= 4194304:
            raise Denied("Invalid process ID")
        allowed = {"Name", "State", "Pid", "PPid", "Uid", "Gid", "Threads", "VmRSS", "VmSize"}
        return {
            key: value.strip()
            for line in Path(f"/proc/{pid}/status").read_text().splitlines()
            if ":" in line
            for key, value in [line.split(":", 1)]
            if key in allowed
        }
