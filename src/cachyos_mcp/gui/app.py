"""Native Qt settings UI for all fields of the agent policy."""

import argparse
import difflib
import json
import os
import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import GROUPS, PROJECT, Settings
from .store import backups, read_snapshot, render, save
from .widgets import FolderList

GROUP_DESCRIPTIONS = {
    "system": "OS, kernel, CPU, memory, disks, identity and session",
    "hardware": "GPU, NVIDIA driver, temperatures, USB and PCI",
    "processes": "Process lists and selected process details",
    "network": "Interfaces, routes and listening ports",
    "packages": "Read installed and repository package information",
    "systemd": "Inspect system services; create and control approved user services",
    "journal": "Read journal messages, boot errors and boot timing",
    "filesystem": "Inspect files; approved file, script and directory changes",
    "kde": "Inspect Plasma; create desktop launchers and widget projects",
    "development": "Approved project Git reads and changes",
    "privileged": "Allowlisted package and system-service actions using sudo",
}
LABELS = {
    "allowed_project_directories": "Project folders",
    "allowed_writable_directories": "Writable folders",
    "enabled_tool_groups": "Tool groups",
    "user_changes_enabled": "User-level changes",
    "privileged_enabled": "Privileged operations",
    "allowed_packages": "Allowed packages",
    "allowed_services": "Allowed system services",
    "max_command_timeout": "Command timeout",
    "max_output_size": "Command output limit",
    "max_file_size": "File read/write limit",
    "logging_level": "Logging level",
    "log_directory": "Audit folder",
    "log_max_bytes": "Audit file size",
    "log_backups": "Audit backups",
}


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class SettingsWindow(QMainWindow):
    def __init__(self, path: Path):
        super().__init__()
        self.snapshot = read_snapshot(path)
        self.loading = True
        self.fields = {}
        self.groups = {}
        self.setWindowTitle("CachyOS Agent Settings")
        self.resize(1060, 790)
        self.setMinimumSize(820, 620)
        container = QWidget()
        self.setCentralWidget(container)
        outer = QVBoxLayout(container)
        heading = QLabel("CachyOS Agent Settings")
        heading.setStyleSheet("font-size: 24px; font-weight: 600; padding: 8px 0;")
        outer.addWidget(heading)
        outer.addWidget(label("Control what your local MCP agent can access and change."))
        self.path_label = label(str(self.snapshot.path))
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.path_label)
        body = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(180)
        self.navigation.addItems(
            ["Overview", "Allowed folders", "Permissions & tools", "Execution limits", "Logging"]
        )
        self.pages = QStackedWidget()
        body.addWidget(self.navigation)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.overview = self.page(
            "Agent policy",
            "Changes are saved to the agent’s existing settings file. Restart your MCP clients after saving to apply them.",
        )
        self.summary = label("")
        self.overview.addWidget(self.summary)
        self.client_summary = label(self.client_status())
        self.overview.addWidget(self.client_summary)
        self.overview.addWidget(
            label(
                "Read-only tools need no server confirmation. User changes require approval. Privileged changes also require enabled policy, exact allowlists and existing sudo authentication."
            )
        )
        self.overview.addWidget(
            label(
                "The agent cannot edit this app’s policy through its file tools. Disk formatting, arbitrary root commands, sudoers changes and other unsupported actions remain blocked."
            )
        )
        overview_buttons = QHBoxLayout()
        for title, callback in [
            ("Read-only draft", self.read_only),
            ("Import policy…", self.import_policy),
            ("Export draft…", self.export_policy),
            ("Restore backup…", self.restore_backup),
            ("Open documentation", self.open_docs),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            overview_buttons.addWidget(button)
        self.overview.addLayout(overview_buttons)
        self.overview.addStretch()
        folders = self.page(
            "Allowed folders",
            "Choose narrow folders under your home directory. Symlink paths, credentials and the server’s own files remain protected by the agent.",
        )
        self.projects = FolderList(
            "Project folders: Git operations and generated Plasma widget projects can use these folders."
        )
        self.writable = FolderList(
            "Writable folders: file, script, launcher and user-service changes can use these folders."
        )
        self.fields["allowed_project_directories"] = self.projects
        self.fields["allowed_writable_directories"] = self.writable
        folders.addWidget(self.projects)
        folders.addWidget(self.writable)
        self.projects.changed.connect(self.changed)
        self.writable.changed.connect(self.changed)
        permissions = self.page(
            "Permissions and tools",
            "Enable the capabilities you want the agent to advertise. Uncheck a group to remove its tools after the client restarts.",
        )
        for group in sorted(GROUPS):
            checkbox = QCheckBox(group.capitalize() + " — " + GROUP_DESCRIPTIONS[group])
            checkbox.setToolTip(GROUP_DESCRIPTIONS[group])
            checkbox.toggled.connect(self.changed)
            self.groups[group] = checkbox
            permissions.addWidget(checkbox)
        self.user_changes = QCheckBox(
            "Allow user-level changes (files, launchers, user services and Git)"
        )
        self.user_changes.toggled.connect(self.changed)
        self.fields["user_changes_enabled"] = self.user_changes
        permissions.addWidget(self.user_changes)
        self.privileged = QCheckBox("Allow privileged operations")
        self.privileged.setToolTip(
            "Requires the privileged tool group, allowlisted actions, approval and sudo authentication."
        )
        self.privileged.toggled.connect(self.changed)
        self.fields["privileged_enabled"] = self.privileged
        permissions.addWidget(self.privileged)
        permissions.addWidget(
            label(
                "Sudo policy stays in force. Enabling this option never grants arbitrary root commands or passwordless sudo. Review package dependencies before approval."
            )
        )
        allowlists = QHBoxLayout()
        for key, title, hint in [
            (
                "allowed_packages",
                "Allowed packages",
                "One official repository package per line. Example: blender",
            ),
            (
                "allowed_services",
                "Allowed system services",
                "One unit per line. Example: bluetooth.service",
            ),
        ]:
            section = QVBoxLayout()
            section.addWidget(label(title))
            editor = QPlainTextEdit()
            editor.setPlaceholderText(hint)
            editor.setMaximumHeight(140)
            editor.textChanged.connect(self.changed)
            self.fields[key] = editor
            section.addWidget(editor)
            section.addWidget(label(hint))
            allowlists.addLayout(section)
        permissions.addLayout(allowlists)
        limits = self.page(
            "Execution limits",
            "Limits apply to each command or file operation. Larger limits increase the agent’s resource budget.",
        )
        form = QFormLayout()
        for key, title, suffix in [
            ("max_command_timeout", "Command timeout", " seconds"),
            ("max_output_size", "Combined stdout/stderr limit", " bytes"),
            ("max_file_size", "File read/write limit", " bytes"),
        ]:
            form.addRow(title, self.spin(key, suffix))
        limits.addLayout(form)
        limits.addWidget(
            label(
                "For lengthy package installs, also increase your MCP client’s tool timeout above this command timeout. Client timeouts are maintained in the client’s own settings."
            )
        )
        limits.addStretch()
        logging = self.page(
            "Logging",
            "Audit records are always enabled. Their contents are sanitized, and rotated files keep disk use bounded.",
        )
        form = QFormLayout()
        combo = QComboBox()
        combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        combo.currentTextChanged.connect(self.changed)
        self.fields["logging_level"] = combo
        form.addRow("Server diagnostic level", combo)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.log_path = QLineEdit()
        self.log_path.textChanged.connect(self.changed)
        self.fields["log_directory"] = self.log_path
        row_layout.addWidget(self.log_path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_log)
        row_layout.addWidget(browse)
        form.addRow("Audit folder", row)
        form.addRow("Size per audit file", self.spin("log_max_bytes", " bytes"))
        form.addRow("Rotated backups", self.spin("log_backups", " files"))
        logging.addLayout(form)
        self.log_budget = label("")
        logging.addWidget(self.log_budget)
        logging.addWidget(
            label(
                "Logs keep timestamps, tools, permission levels and outcomes. File contents, command output, passwords and tokens are not recorded. Diagnostic verbosity does not disable auditing."
            )
        )
        open_logs = QPushButton("Open saved audit folder")
        open_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(self.snapshot.settings.log_directory).expanduser()))
            )
        )
        logging.addWidget(open_logs)
        logging.addStretch()
        self.status = label("")
        self.status.setMinimumHeight(50)
        outer.addWidget(self.status)
        footer = QHBoxLayout()
        for title, callback in [
            ("Reload from disk", self.reload),
            ("Secure defaults", self.defaults),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            footer.addWidget(button)
        footer.addStretch()
        self.preview_button = QPushButton("Review changes")
        self.preview_button.clicked.connect(lambda: self.review(False))
        footer.addWidget(self.preview_button)
        self.save_button = QPushButton("Save settings…")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save_changes)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)
        self.navigation.setCurrentRow(0)
        self.populate(self.snapshot.settings)

    def page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QLabel(title)
        header.setStyleSheet("font-size: 19px; font-weight: 600; padding-top: 8px;")
        layout.addWidget(header)
        layout.addWidget(label(description))
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        return layout

    def spin(self, key, suffix):
        widget = QSpinBox()
        constraints = Settings.model_json_schema()["properties"][key]
        widget.setRange(constraints["minimum"], constraints["maximum"])
        widget.setSuffix(suffix)
        widget.valueChanged.connect(self.changed)
        self.fields[key] = widget
        return widget

    def populate(self, settings):
        self.loading = True
        for key, value in settings.model_dump().items():
            if key == "enabled_tool_groups":
                for group, checkbox in self.groups.items():
                    checkbox.setChecked(group in value)
                continue
            widget = self.fields[key]
            if isinstance(widget, FolderList):
                widget.set_values(value)
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText("\n".join(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            else:
                widget.setText(value)
        self.loading = False
        self.changed()

    def values(self):
        selected = {group for group, checkbox in self.groups.items() if checkbox.isChecked()}
        prior = self.snapshot.settings.enabled_tool_groups
        values = {
            "enabled_tool_groups": [group for group in prior if group in selected]
            + sorted(selected - set(prior))
        }
        for key, widget in self.fields.items():
            if isinstance(widget, FolderList):
                values[key] = widget.values()
            elif isinstance(widget, QPlainTextEdit):
                values[key] = list(
                    dict.fromkeys(
                        line.strip() for line in widget.toPlainText().splitlines() if line.strip()
                    )
                )
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                values[key] = widget.value()
            elif isinstance(widget, QComboBox):
                values[key] = widget.currentText()
            else:
                values[key] = widget.text().strip()
        return values

    def validated(self):
        return Settings.model_validate(self.values())

    def dirty(self):
        return self.values() != self.snapshot.settings.model_dump()

    def changed(self, *_):
        if self.loading:
            return
        try:
            settings = self.validated()
        except ValidationError as error:
            messages = [
                LABELS.get(str(e["loc"][0]), str(e["loc"][0])) + ": " + e["msg"]
                for e in error.errors(include_input=False)
            ]
            self.status.setText("Cannot save: " + "; ".join(messages))
            self.save_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            return
        dirty = self.dirty()
        self.setWindowTitle("CachyOS Agent Settings" + (" • Unsaved changes" if dirty else ""))
        self.save_button.setEnabled(dirty)
        self.preview_button.setEnabled(dirty)
        note = (
            "Unsaved changes. Review and save to update the policy."
            if dirty
            else "Settings match the saved policy."
        )
        if settings.privileged_enabled and "privileged" not in settings.enabled_tool_groups:
            note += " Privileged tools are hidden because their group is disabled."
        self.status.setText(note)
        self.summary.setText(
            f"Enabled tool groups: {len(settings.enabled_tool_groups)} of {len(GROUPS)}\nProject folders: {len(settings.allowed_project_directories)} · Writable folders: {len(settings.allowed_writable_directories)}\nPrivileged operations: {'enabled' if settings.privileged_enabled else 'disabled'}\nCommand timeout: {settings.max_command_timeout} seconds"
        )
        budget = settings.log_max_bytes * (settings.log_backups + 1)
        self.log_budget.setText(
            f"Maximum audit storage: {budget / 1048576:.2f} MiB across the active file and {settings.log_backups} backups."
        )

    def review(self, saving):
        settings = self.validated()
        after = render(self.snapshot, settings).decode("utf-8")
        diff = "".join(
            difflib.unified_diff(
                self.snapshot.raw.decode("utf-8").splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="Saved policy",
                tofile="Proposed policy",
            )
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Review agent settings")
        dialog.resize(850, 610)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            label(
                "A private backup is kept before saving. Restart Claude Code, Codex and Gemini CLI afterward to apply the new policy."
            )
        )
        if settings.privileged_enabled:
            layout.addWidget(
                label(
                    "This policy allows privileged operations for the listed packages and services. Sudo authentication and per-action approval remain required."
                )
            )
        preview = QPlainTextEdit(diff)
        preview.setReadOnly(True)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            if saving
            else QDialogButtonBox.StandardButton.Close
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def save_changes(self):
        try:
            settings = self.validated()
            if not self.review(True):
                return
            self.snapshot, backup = save(self.snapshot, settings)
            self.populate(self.snapshot.settings)
            self.status.setText(
                "Saved. Restart Claude Code, Codex and Gemini CLI to apply these settings. Backup: "
                + str(backup)
            )
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Settings were not saved", str(error))

    def discard_ok(self):
        if not self.dirty():
            return True
        return (
            QMessageBox.question(
                self,
                "Unsaved changes",
                "Discard your unsaved settings?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Discard
        )

    def reload(self):
        if not self.discard_ok():
            return
        try:
            snapshot = read_snapshot(self.snapshot.path)
            self.snapshot = snapshot
            self.populate(snapshot.settings)
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Could not reload", str(error))

    def read_only(self):
        self.user_changes.setChecked(False)
        self.privileged.setChecked(False)

    def defaults(self):
        if self.discard_ok():
            self.populate(Settings())

    def import_policy(self):
        if not self.discard_ok():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import policy as a draft", str(Path.home()), "TOML policy (*.toml)"
        )
        if path:
            self.import_path(Path(path))

    def import_path(self, path):
        try:
            self.populate(read_snapshot(path).settings)
            self.status.setText(
                "Policy loaded as a draft. Review and save to apply it to "
                + str(self.snapshot.path)
            )
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Invalid policy", str(error))

    def export_policy(self):
        try:
            raw = render(self.snapshot, self.validated())
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export draft to a new file",
                str(Path.home() / "cachyos-policy.toml"),
                "TOML policy (*.toml)",
            )
            if path:
                from ..security import Paths

                destination = Path(path).absolute()
                with Paths(Settings()).parent(destination) as (fd, name):
                    from .store import _write

                    _write(fd, name, raw)
                self.status.setText("Draft exported. The active agent policy has not changed.")
        except (ValueError, OSError) as error:
            QMessageBox.critical(
                self,
                "Could not export",
                str(error) + "\nChoose a new filename; existing files are not overwritten.",
            )

    def restore_backup(self):
        if not self.discard_ok():
            return
        try:
            choices = backups(self.snapshot)
            if not choices:
                QMessageBox.information(
                    self,
                    "Policy backups",
                    "No backups yet. The app keeps the five most recent saves.",
                )
                return
            choice, accepted = QInputDialog.getItem(
                self,
                "Restore backup as a draft",
                "Backup (UTC timestamp):",
                [p.name for p in choices],
                0,
                False,
            )
            if accepted:
                self.import_path(next(p for p in choices if p.name == choice))
        except (ValueError, OSError) as error:
            QMessageBox.critical(self, "Could not restore", str(error))

    def browse_log(self):
        path = QFileDialog.getExistingDirectory(self, "Audit folder", str(Path.home()))
        if path:
            self.log_path.setText(path)

    def open_docs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PROJECT / "README.md")))

    @staticmethod
    def client_status():
        status = []
        configs = [
            ("Claude Code", Path.home() / ".claude.json"),
            ("Gemini CLI", Path.home() / ".gemini/settings.json"),
            (
                "Codex",
                Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml",
            ),
        ]
        for name, path in configs:
            try:
                raw = path.read_text()
                data = tomllib.loads(raw) if path.suffix == ".toml" else json.loads(raw)
                entries = data.get("mcp_servers" if name == "Codex" else "mcpServers", {})
                registered = "cachyos-system" in entries
                status.append(
                    f"{name}: {'registered' if registered else 'no user-level registration found'}"
                )
            except (OSError, ValueError):
                status.append(f"{name}: user registration could not be read")
        return "Client configuration (not a live connection check):\n" + "\n".join(status)

    def closeEvent(self, event):
        event.accept() if self.discard_ok() else event.ignore()


def main():
    parser = argparse.ArgumentParser(
        description="Maintain CachyOS MCP agent policy using a native GUI"
    )
    parser.add_argument("--config", type=Path, default=PROJECT / "config/settings.toml")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run the settings app as your regular user, not root")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CachyOS Agent Settings")
    app.setOrganizationName("CachyOS MCP")
    app.setDesktopFileName("cachyos-agent-settings")
    app.setWindowIcon(QIcon.fromTheme("preferences-system"))
    try:
        window = SettingsWindow(args.config)
    except (ValueError, OSError) as error:
        QMessageBox.critical(None, "Cannot open agent settings", str(error))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
