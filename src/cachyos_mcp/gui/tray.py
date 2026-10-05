"""Desktop tray lifecycle; keeps unsaved settings in memory until explicit exit."""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class SettingsTray:
    def __init__(self, window):
        self.window = window
        self.app = QApplication.instance()
        icon = QIcon.fromTheme("preferences-system")
        if icon.isNull():
            icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.icon = QSystemTrayIcon(icon, window)
        self.icon.setToolTip("CachyOS Agent Settings")
        self.menu = QMenu(window)
        self.show_action = self.menu.addAction("Open settings")
        self.show_action.triggered.connect(self.show_window)
        self.hide_action = self.menu.addAction("Hide settings window")
        self.hide_action.triggered.connect(self.hide_window)
        self.menu.addSeparator()
        self.menu.addAction("Open documentation", window.open_docs)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("Quit")
        self.quit_action.triggered.connect(self.quit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.activated)
        self.app.aboutToQuit.connect(self.icon.hide)
        window.tray = self
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.app.setQuitOnLastWindowClosed(False)
            self.icon.show()

    def available(self):
        return self.icon.isVisible() and QSystemTrayIcon.isSystemTrayAvailable()

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def hide_window(self):
        if self.available():
            self.window.hide()

    def activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def quit(self):
        if self.window.dirty():
            self.show_window()
        if not self.window.discard_ok():
            return
        self.window.quitting = True
        self.icon.hide()
        self.window.close()
        self.app.quit()
