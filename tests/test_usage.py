"""Quota providers handle missing, expired, malformed and asynchronous readings."""

import json
import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from cachyos_mcp.gui.usage import INTERVAL_MS, UsageMonitor, claude_windows, codex_windows, window


@pytest.fixture
def monitor():
    app = QApplication.instance() or QApplication([])
    value = UsageMonitor(lambda: None)
    yield value
    value.stop()
    assert app is not None


def test_account_windows_use_actual_duration_and_bucket():
    result = {
        "rateLimitsByLimitId": {
            "codex": {
                "primary": {
                    "usedPercent": 42.5,
                    "windowDurationMins": 10080,
                    "resetsAt": 2000000000,
                },
                "secondary": {"usedPercent": 0, "windowDurationMins": 300, "resetsAt": 2000000000},
            },
            "codex_review": {
                "primary": {"usedPercent": 99, "windowDurationMins": 300, "resetsAt": 2000000000}
            },
        }
    }
    values = codex_windows(result)
    assert values["seven_day"]["left"] == 57.5
    assert values["five_hour"]["used"] == 0
    assert values["five_hour"]["left"] == 100
    assert (
        codex_windows(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 5, "windowDurationMins": 15, "resetsAt": 2000000000}
                }
            }
        )
        == {}
    )


@pytest.mark.parametrize("used", [None, True, "4", -1, 101, float("nan"), float("inf")])
def test_invalid_percentages_are_not_displayed(used):
    assert window({"used": used, "reset": 2000000000}, "used", "reset") is None


@pytest.mark.parametrize("data", [None, [], {}, {"rate_limits": None}, {"rate_limits": []}])
def test_missing_claude_quotas_are_unknown(data):
    assert not any(claude_windows(data).values())


def test_claude_submission_strips_unrelated_data_and_expires_windows(monitor):
    now = time.time()
    monitor.SubmitClaude(
        json.dumps(
            {
                "prompt": "private content",
                "access_token": "secret",
                "rate_limits": {
                    "five_hour": {"used_percentage": 23.5, "resets_at": now + 3600},
                    "seven_day": {"used_percentage": 44, "resets_at": now - 1},
                },
            }
        )
    )
    payload = monitor.GetUsage()
    assert "private" not in payload and "secret" not in payload
    reading = json.loads(payload)["agents"][1]
    assert reading["windows"]["five_hour"]["left"] == 76.5
    assert reading["windows"]["seven_day"] is None
    monitor.SubmitClaude("invalid")
    assert monitor.GetUsage()
    assert monitor.timer.interval() == INTERVAL_MS == 3000


class FakeProcess:
    def __init__(self):
        self.output = b""
        self.sent = []
        self.killed = False

    def readAllStandardOutput(self):
        output, self.output = self.output, b""
        return output

    def write(self, data):
        self.sent.append(json.loads(data))

    def state(self):
        return QProcess.ProcessState.NotRunning

    def kill(self):
        self.killed = True


def test_fragmented_protocol_and_request_overlap(monitor):
    process = FakeProcess()
    monitor.process = process
    monitor.request("initialize", {})
    process.output = b'{"id":1,"res'
    monitor.receive()
    assert monitor.pending[1] == "initialize"
    process.output = b'ult":{}}\n'
    monitor.receive()
    assert process.sent[-2] == {"method": "initialized"}
    assert process.sent[-1]["method"] == "account/rateLimits/read"
    count = len(process.sent)
    monitor.refresh()
    assert len(process.sent) == count
    process.output = (
        json.dumps(
            {
                "id": 2,
                "result": {
                    "rateLimits": {
                        "primary": {
                            "usedPercent": 20,
                            "windowDurationMins": 300,
                            "resetsAt": 2000000000,
                        }
                    }
                },
            }
        ).encode()
        + b"\n"
    )
    monitor.receive()
    assert monitor.readings["Codex"]["windows"]["five_hour"]["left"] == 80
    assert monitor.pending is None


def test_timeout_kills_process_and_backs_off(monitor):
    process = FakeProcess()
    monitor.process = process
    monitor.pending = (1, "account/rateLimits/read", time.monotonic() - 16)
    monitor.refresh()
    assert process.killed
    assert monitor.retry_at > time.monotonic()
    assert "timed out" in monitor.readings["Codex"]["status"]


@pytest.mark.parametrize("client", ["Codex", "Claude Code", "Gemini CLI"])
def test_bridge_opens_selected_console(monitor, client):
    calls = []
    monitor.open_console = calls.append
    monitor.bridge.OpenConsole(client)
    assert calls == [client]


def test_bridge_rejects_unknown_console(monitor):
    calls = []
    monitor.open_console = calls.append
    monitor.bridge.OpenConsole("sh -c arbitrary-command")
    assert calls == []


def test_hidden_agents_are_not_published(monitor):
    monitor.visibility.set_visible("Gemini CLI", False)
    agents = json.loads(monitor.GetUsage())["agents"]
    assert [agent["name"] for agent in agents] == ["Codex", "Claude Code"]
    assert all(isinstance(agent["running"], int) for agent in agents)


def test_bridge_shuts_down_only_known_clients(monitor, monkeypatch):
    from cachyos_mcp.gui import usage

    calls = []
    monkeypatch.setattr(usage, "shut_down", lambda client, *args: calls.append(client) or [])
    monitor.bridge.Shutdown("Codex")
    monitor.bridge.Shutdown("sh -c arbitrary-command")
    assert calls == ["Codex"]
