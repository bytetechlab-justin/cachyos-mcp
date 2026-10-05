"""The sole subprocess boundary. Internal argv only; never a shell."""

import asyncio
import os
import signal
import time

SAFE_PATH = "/usr/bin:/bin"


class Executor:
    def __init__(self, settings):
        self.settings = settings

    async def run(
        self,
        argv: list[str],
        timeout: int | None = None,
        cwd: str | None = None,
        cwd_fd: int | None = None,
    ) -> dict:
        started = time.monotonic()
        result = {
            "success": False,
            "command": argv,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "truncated": False,
        }
        if not argv or any(not isinstance(a, str) or "\x00" in a for a in argv):
            return result | {"error": "invalid_command", "duration_ms": 0}
        env = {
            k: os.environ[k]
            for k in (
                "HOME",
                "USER",
                "LOGNAME",
                "XDG_RUNTIME_DIR",
                "DBUS_SESSION_BUS_ADDRESS",
                "DISPLAY",
                "WAYLAND_DISPLAY",
            )
            if k in os.environ
        }
        env.update(
            PATH=SAFE_PATH,
            LANG="C.UTF-8",
            LC_ALL="C.UTF-8",
            SYSTEMD_PAGER="",
            PAGER="cat",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_ATTR_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_TERMINAL_PROMPT="0",
        )
        proc = None
        buffers = [bytearray(), bytearray()]
        size = 0

        async def drain(stream, index):
            nonlocal size
            while chunk := await stream.read(4096):
                remaining = self.settings.max_output_size - size
                buffers[index].extend(chunk[: max(0, remaining)])
                size += len(chunk)
                if size > self.settings.max_output_size:
                    result["truncated"] = True
                    kill()
                    break

        def kill():
            if proc:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=f"/proc/self/fd/{cwd_fd}" if cwd_fd is not None else cwd,
                pass_fds=(cwd_fd,) if cwd_fd is not None else (),
                env=env,
                start_new_session=True,
            )
            tasks = [
                asyncio.create_task(drain(proc.stdout, 0)),
                asyncio.create_task(drain(proc.stderr, 1)),
            ]
            try:
                async with asyncio.timeout(
                    min(
                        timeout or self.settings.max_command_timeout,
                        self.settings.max_command_timeout,
                    )
                ):
                    await asyncio.gather(*tasks, proc.wait())
            except TimeoutError:
                result["error"] = "timeout"
                kill()
                await proc.wait()
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            result["exit_code"] = proc.returncode
            result["success"] = (
                proc.returncode == 0 and not result["truncated"] and "error" not in result
            )
            if result["truncated"]:
                result["error"] = "output_limit"
        except FileNotFoundError:
            result["error"] = "missing_executable"
            result["hint"] = f"Install the host utility providing {argv[0]} manually."
        except OSError:
            result["error"] = "execution_failed"
        finally:
            if proc and proc.returncode is None:
                kill()
                await proc.wait()
            result["duration_ms"] = round((time.monotonic() - started) * 1000)
            result["stdout"] = buffers[0].decode("utf-8", errors="replace")
            result["stderr"] = buffers[1].decode("utf-8", errors="replace")
        return result
