"""Quota normalization and asynchronous desktop usage service (no model turns)."""

import json
import math
import os
import shutil
import signal
import time

from PySide6.QtCore import ClassInfo, QObject, QProcess, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

from .consoles import CLIENTS, AgentVisibility, processes, shut_down

SERVICE = "org.cachyos.AgentUsage"
OBJECT_PATH = "/Usage"
INTERVAL_MS = 3000
# Time a client gets to exit cleanly before it is killed.
GRACE_MS = 3000


def window(value, percent_key, reset_key):
    """Keep only validated public quota fields; missing is never treated as zero."""
    if not isinstance(value, dict):
        return None
    used, reset = value.get(percent_key), value.get(reset_key)
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    if not math.isfinite(used) or not 0 <= used <= 100:
        return None
    if isinstance(reset, bool) or not isinstance(reset, (int, float)):
        return None
    if not math.isfinite(reset) or reset <= 0:
        return None
    return {"used": used, "left": 100 - used, "resets_at": reset}


def codex_windows(result):
    if not isinstance(result, dict):
        return {}
    buckets = result.get("rateLimitsByLimitId")
    # Never display a model-specific or review bucket as the account's Codex quota.
    limits = buckets.get("codex") if isinstance(buckets, dict) else result.get("rateLimits")
    if not isinstance(limits, dict):
        return {}
    normalized = {}
    for key in ("primary", "secondary"):
        value = limits.get(key)
        if not isinstance(value, dict):
            continue
        duration = value.get("windowDurationMins")
        name = "five_hour" if duration == 300 else "seven_day" if duration == 10080 else None
        if name:
            normalized[name] = window(value, "usedPercent", "resetsAt")
    return normalized


def claude_windows(data):
    limits = data.get("rate_limits", {}) if isinstance(data, dict) else {}
    if not isinstance(limits, dict):
        return {}
    return {
        key: window(limits.get(key), "used_percentage", "resets_at")
        for key in ("five_hour", "seven_day")
    }


class UsageMonitor(QObject):
    """One read-only Codex app-server subprocess, shared over the user's session bus."""

    def __init__(self, show_settings, parent=None, *, open_console=None, visibility=None):
        super().__init__(parent)
        self.show_settings = show_settings
        self.open_console = open_console
        self.visibility = visibility or AgentVisibility()
        self.readings = {
            "Codex": {"windows": {}, "updated_at": None, "status": "Waiting for Codex"},
            "Claude Code": {
                "windows": {},
                "updated_at": None,
                "status": "Open Claude Code from the tray to enable usage reports",
            },
            "Gemini CLI": {
                "windows": {},
                "updated_at": None,
                "status": "Gemini does not report 5-hour / 7-day quotas",
            },
        }
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.started.connect(self.initialize)
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.buffer = bytearray()
        self.pending = None
        self.sequence = 0
        self.initialized = False
        self.retry_at = 0
        self.stopping = False
        self.timer = QTimer(self)
        self.timer.setInterval(INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.bus = QDBusConnection.sessionBus()
        self.registered = False
        self.bridge = UsageBridge(self)

    def start(self):
        # A second settings instance must not create a duplicate quota poller.
        if not self.bus.registerService(SERVICE):
            return False
        if not self.bus.registerObject(
            OBJECT_PATH, self.bridge, QDBusConnection.RegisterOption.ExportAllSlots
        ):
            self.bus.unregisterService(SERVICE)
            return False
        self.registered = True
        self.timer.start()
        self.refresh()
        return True

    def GetUsage(self):
        now = time.time()
        agents = []
        running = processes()
        for name, reading in self.readings.items():
            if not self.visibility.visible(name):
                continue
            windows = {
                key: value if value and value["resets_at"] > now else None
                for key, value in reading["windows"].items()
            }
            agents.append(
                {"name": name, **reading, "windows": windows, "running": len(running[name])}
            )
        return json.dumps({"agents": agents, "generated_at": now}, allow_nan=False)

    def ShowSettings(self):
        self.show_settings()

    def OpenConsole(self, client):
        if client in CLIENTS and self.open_console is not None:
            self.open_console(client)

    def Shutdown(self, client):
        if client not in CLIENTS:
            return
        pids = shut_down(client)
        if pids:
            # Re-matched by name before killing, so a reused PID is never signalled.
            QTimer.singleShot(GRACE_MS, self, lambda: shut_down(client, signal.SIGKILL, pids))

    def SubmitClaude(self, payload):
        if len(payload) > 4096:
            return
        try:
            data = json.loads(payload)
        except ValueError:
            return
        values = claude_windows(data)
        self.readings["Claude Code"] = {
            "windows": values,
            "updated_at": time.time(),
            "status": "Latest Claude status-line report"
            if any(values.values())
            else "Claude has not reported subscription quotas",
        }

    def unavailable(self, status):
        self.readings["Codex"]["status"] = status

    def refresh(self):
        now = time.monotonic()
        if self.stopping or now < self.retry_at:
            return
        if self.pending is not None:
            if now - self.pending[2] > 15:
                self.unavailable("Codex usage request timed out; retrying")
                self.retry_at = now + 30
                self.process.kill()
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            executable = shutil.which(
                "codex",
                path=os.pathsep.join(
                    [os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/usr/bin", "/bin"]
                ),
            )
            if not executable:
                self.unavailable("Codex is not installed")
                self.retry_at = now + 60
                return
            self.buffer.clear()
            self.initialized = False
            self.process.start(executable, ["app-server", "--listen", "stdio://"])
        elif self.initialized:
            self.request("account/rateLimits/read")

    def initialize(self):
        self.request(
            "initialize",
            {"clientInfo": {"name": "cachyos_usage", "title": "CachyOS Usage", "version": "0.1.0"}},
        )

    def send(self, message):
        self.process.write((json.dumps(message) + "\n").encode())

    def request(self, method, params=None):
        self.sequence += 1
        self.pending = (self.sequence, method, time.monotonic())
        message = {"id": self.sequence, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def receive(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer) > 1048576:
            self.process.kill()
            self.buffer.clear()
            return
        while b"\n" in self.buffer:
            line, _, self.buffer = self.buffer.partition(b"\n")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if not self.pending or message.get("id") != self.pending[0]:
                continue
            method = self.pending[1]
            self.pending = None
            if "error" in message:
                self.unavailable("Codex usage unavailable; check Codex sign-in")
                self.retry_at = time.monotonic() + 60
                if method == "initialize":
                    self.process.kill()
                continue
            if method == "initialize":
                self.initialized = True
                self.send({"method": "initialized"})
                self.request("account/rateLimits/read")
            else:
                values = codex_windows(message.get("result"))
                self.readings["Codex"] = {
                    "windows": values,
                    "updated_at": time.time(),
                    "status": "Live account quota"
                    if any(values.values())
                    else "Codex has not reported 5-hour / 7-day quotas",
                }

    def process_error(self, *_):
        self.unavailable("Codex usage process unavailable; retrying")
        self.retry_at = time.monotonic() + 30
        self.pending = None

    def process_finished(self, *_):
        self.pending = None
        self.initialized = False
        self.retry_at = max(self.retry_at, time.monotonic() + 30)
        if not self.stopping:
            self.unavailable("Codex usage process stopped; retrying")

    def stop(self):
        self.stopping = True
        self.timer.stop()
        if self.registered:
            self.bus.unregisterObject(OBJECT_PATH)
            self.bus.unregisterService(SERVICE)
            self.registered = False
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)


@ClassInfo(**{"D-Bus Interface": SERVICE})
class UsageBridge(QObject):
    """Expose the intended desktop actions under a stable interface name."""

    def __init__(self, monitor):
        super().__init__(monitor)
        self.monitor = monitor

    @Slot(result=str)
    def GetUsage(self):
        return self.monitor.GetUsage()

    @Slot()
    def ShowSettings(self):
        self.monitor.ShowSettings()

    @Slot(str)
    def OpenConsole(self, client):
        self.monitor.OpenConsole(client)

    @Slot(str)
    def Shutdown(self, client):
        if client not in CLIENTS:
            return
        pids = shut_down(client)
        if pids:
            # Re-matched by name before killing, so a reused PID is never signalled.
            QTimer.singleShot(GRACE_MS, self, lambda: shut_down(client, signal.SIGKILL, pids))

    def SubmitClaude(self, payload):
        self.monitor.SubmitClaude(payload)
