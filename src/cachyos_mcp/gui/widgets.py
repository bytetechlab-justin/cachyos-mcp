from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FolderList(QWidget):
    changed = Signal()

    def __init__(self, description: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.list = QListWidget()
        self.list.setMinimumHeight(145)
        self.list.itemDoubleClicked.connect(lambda _: self.edit())
        layout.addWidget(self.list)
        buttons = QHBoxLayout()
        for title, callback in [
            ("Browse…", self.browse),
            ("Add path…", self.add),
            ("Edit", self.edit),
            ("Remove", self.remove),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def values(self):
        return [self.list.item(i).text() for i in range(self.list.count())]

    def set_values(self, values):
        self.list.clear()
        self.list.addItems(values)

    def append(self, value):
        value = value.strip()
        if value and value not in self.values():
            self.list.addItem(value)
            self.changed.emit()

    def browse(self):
        value = QFileDialog.getExistingDirectory(self, "Allow folder", str(Path.home()))
        if value:
            self.append(value)

    def add(self):
        value, accepted = QInputDialog.getText(self, "Allow folder", "Absolute path or ~/path:")
        if accepted:
            self.append(value)

    def edit(self):
        item = self.list.currentItem()
        if item is None:
            return
        value, accepted = QInputDialog.getText(
            self, "Edit allowed folder", "Folder:", text=item.text()
        )
        if accepted and value.strip():
            item.setText(value.strip())
            self.changed.emit()

    def remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self.changed.emit()
