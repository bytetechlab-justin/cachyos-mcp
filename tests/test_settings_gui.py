"""GUI/persistence tests use temporary policies; never change the live agent policy."""

import os

import pytest

pytest.importorskip("tomlkit")
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from cachyos_mcp.config import PROJECT, Settings
from cachyos_mcp.gui.app import SettingsWindow
from cachyos_mcp.gui.store import ConflictError, read_snapshot, save


@pytest.fixture
def policy(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_bytes((PROJECT / "config/settings.toml").read_bytes())
    return path


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_save_preserves_comments_and_backups(policy):
    original = policy.read_bytes()
    snapshot = read_snapshot(policy)
    settings = Settings.model_validate(snapshot.settings.model_dump() | {"max_command_timeout": 60})
    result, backup = save(snapshot, settings)
    assert backup.read_bytes() == original
    assert result.settings.max_command_timeout == 60
    assert "# Administrator-owned policy" in policy.read_text()
    assert policy.stat().st_mode & 0o077 == 0
    assert backup.stat().st_mode & 0o077 == 0


def test_external_edits_are_not_overwritten(policy):
    snapshot = read_snapshot(policy)
    policy.write_bytes(snapshot.raw + b"\n# external change\n")
    with pytest.raises(ConflictError):
        save(snapshot, snapshot.settings)
    assert policy.read_bytes().endswith(b"# external change\n")


def test_backup_rotation(policy):
    snapshot = read_snapshot(policy)
    for number in range(8):
        settings = Settings.model_validate(
            snapshot.settings.model_dump() | {"max_command_timeout": 31 + number}
        )
        snapshot, _ = save(snapshot, settings)
    assert len(list((policy.parent / ".settings-backups").glob("*.toml"))) == 5


def test_policy_and_backup_symlinks_are_refused(policy, tmp_path):
    link = tmp_path / "link.toml"
    link.symlink_to(policy)
    with pytest.raises(OSError):
        read_snapshot(link)
    snapshot = read_snapshot(policy)
    destination = tmp_path / "elsewhere"
    destination.mkdir()
    (tmp_path / ".settings-backups").symlink_to(destination)
    with pytest.raises(OSError):
        save(snapshot, snapshot.settings)
    assert not list(destination.iterdir())


def test_invalid_allowlists_and_audit_path():
    for values in [
        {"allowed_packages": ["--root=/tmp"]},
        {"allowed_services": ["bluetooth"]},
        {"allowed_services": ["bluetooth;id.service"]},
        {"log_directory": "~/../logs"},
    ]:
        with pytest.raises(ValueError):
            Settings.model_validate(values)


def test_every_policy_setting_has_a_control(app, policy):
    window = SettingsWindow(policy)
    assert set(window.fields) | {"enabled_tool_groups"} == set(Settings.model_fields)
    assert window.values() == window.snapshot.settings.model_dump()
    assert not window.save_button.isEnabled()
    window.close()


def test_edit_validate_save_and_reload(app, policy, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: errors.append(a))
    window = SettingsWindow(policy)
    window.fields["allowed_packages"].setPlainText("blender;id")
    assert not window.save_button.isEnabled()
    assert "Allowed packages" in window.status.text()
    window.fields["allowed_packages"].setPlainText("blender\nvlc")
    window.fields["max_command_timeout"].setValue(60)
    window.groups["development"].setChecked(False)
    assert window.save_button.isEnabled()
    monkeypatch.setattr(window, "review", lambda _: True)
    window.save_changes()
    assert not errors
    settings = read_snapshot(policy).settings
    assert settings.allowed_packages == ["blender", "vlc"]
    assert settings.max_command_timeout == 60
    assert "development" not in settings.enabled_tool_groups
    assert not window.dirty()
    assert "Restart" in window.status.text()
    window.reload()
    assert window.values() == settings.model_dump()
    window.close()


def test_import_is_staged_without_changing_policy(app, policy, tmp_path, monkeypatch):
    from cachyos_mcp.gui.store import render

    window = SettingsWindow(policy)
    original = policy.read_bytes()
    imported = tmp_path / "imported.toml"
    imported.write_bytes(render(window.snapshot, Settings(privileged_enabled=True)))
    window.import_path(imported)
    assert window.fields["privileged_enabled"].isChecked()
    assert window.dirty()
    assert policy.read_bytes() == original
    monkeypatch.setattr(window, "discard_ok", lambda: True)
    window.close()


def test_read_only_draft_keeps_inspection_groups(app, policy, monkeypatch):
    window = SettingsWindow(policy)
    window.read_only()
    assert not window.validated().user_changes_enabled
    assert not window.validated().privileged_enabled
    assert "filesystem" in window.validated().enabled_tool_groups
    monkeypatch.setattr(window, "discard_ok", lambda: True)
    window.close()


@pytest.mark.parametrize(
    "contents,expected",
    [
        (
            '{"mcpServers":{"cachyos-system":{"command":"/example/server"}}}',
            "Gemini CLI: registered",
        ),
        ('{"mcpServers":{}}', "Gemini CLI: no user-level registration found"),
        ("invalid JSON", "Gemini CLI: user registration could not be read"),
    ],
)
def test_gemini_client_status(tmp_path, monkeypatch, contents, expected):
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".gemini"
    directory.mkdir()
    (directory / "settings.json").write_text(contents)
    assert expected in SettingsWindow.client_status()


def test_tray_close_preserves_unsaved_changes(app, policy, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    from cachyos_mcp.gui.tray import SettingsTray

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, "isVisible", lambda self: True)
    window = SettingsWindow(policy)
    tray = SettingsTray(window)
    window.fields["max_command_timeout"].setValue(61)
    window.show()
    monkeypatch.setattr(
        window, "discard_ok", lambda: pytest.fail("Hiding must not discard a draft")
    )
    window.close()
    assert not window.isVisible()
    assert window.dirty()
    assert window.fields["max_command_timeout"].value() == 61
    tray.activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()
    window.quitting = True
    window.close()
    app.setQuitOnLastWindowClosed(True)


def test_tray_quit_can_be_cancelled(app, policy, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    from cachyos_mcp.gui.tray import SettingsTray

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window = SettingsWindow(policy)
    tray = SettingsTray(window)
    window.fields["max_command_timeout"].setValue(62)
    monkeypatch.setattr(window, "discard_ok", lambda: False)
    called = []
    monkeypatch.setattr(app, "quit", lambda: called.append(True))
    tray.quit()
    assert not window.quitting
    assert window.isVisible()
    assert not called
    monkeypatch.setattr(window, "discard_ok", lambda: True)
    tray.quit()
    assert window.quitting
    assert called == [True]


def test_no_tray_uses_normal_close(app, policy, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    from cachyos_mcp.gui.tray import SettingsTray

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window = SettingsWindow(policy)
    tray = SettingsTray(window)
    assert not tray.available()
    window.show()
    window.close()
    assert not window.isVisible()
    assert app.quitOnLastWindowClosed()
