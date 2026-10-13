"""Cachy Canvas: a native, local prompt-to-image desktop application."""

import json
import sys
import threading
from dataclasses import replace
from pathlib import Path

from core import (
    CATALOG,
    SearchResult,
    architecture,
    compatibility,
    data_dir,
    hardware,
    installed_models,
    lora_matches,
    search_with_compatibility,
)
from engine import Engine
from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QImageReader, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyledItemDelegate,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

COLORS = {
    "recommended": "#72e39b",
    "marginal": "#ffb45f",
    "offload": "#ffb45f",
    "limited": "#ff7777",
    "unavailable": "#ff7777",
    "incompatible": "#ff7777",
}


def type_icon(kind):
    return QIcon(str(Path(__file__).with_name("lora.svg" if kind == "lora" else "checkpoint.svg")))


class StatusDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if isinstance(foreground, (QColor, QBrush)):
            color = foreground.color() if isinstance(foreground, QBrush) else foreground
            option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


class Task(QThread):
    progress = Signal(str, int)
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.success.emit(self.function(self.progress.emit, self.cancelled.is_set))
        except Exception as error:  # noqa: BLE001 -- third-party errors must cross the Qt thread boundary
            # Never show request headers/tokens in the UI.
            message = str(error)
            import os

            if os.environ.get("HF_TOKEN"):
                message = message.replace(os.environ["HF_TOKEN"], "[redacted]")
            self.failure.emit(message)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cachy Canvas")
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
        self.resize(1160, 800)
        self.engine = Engine()
        self.hw = hardware()
        self.task = None
        self.preview_path = None
        self.models = list(CATALOG)
        self.controls = []
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel("CACHY CANVAS  <span style='color:#7ee0c3'>/ Local image studio</span>")
        title.setStyleSheet("font-size:22px; font-weight:600; margin-bottom:8px")
        layout.addWidget(title)
        self.hardware_label = QLabel()
        self.hardware_label.setWordWrap(True)
        layout.addWidget(self.hardware_label)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.create_tab()
        self.models_tab()
        self.gallery_tab()
        bottom = QHBoxLayout()
        self.status = QLabel("Install a model in Explore models to get started.")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setValue(0)
        self.cancel = QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_task)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.progress)
        bottom.addWidget(self.cancel)
        layout.addLayout(bottom)
        self.setCentralWidget(root)
        self.refresh()

    def button(self, text, function, layout):
        button = QPushButton(text)
        button.clicked.connect(function)
        layout.addWidget(button)
        self.controls.append(button)
        return button

    def create_tab(self):
        tab = QWidget()
        box = QHBoxLayout(tab)
        splitter = QSplitter()
        panel = QWidget()
        form = QVBoxLayout(panel)
        self.model_choice = QComboBox()
        self.model_choice.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.model_choice.setMinimumContentsLength(20)
        self.model_choice.setItemDelegate(StatusDelegate(self.model_choice))
        self.model_choice.currentIndexChanged.connect(self.preset)
        form.addWidget(QLabel("MODEL"))
        form.addWidget(self.model_choice)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Describe the image you want to create…")
        self.prompt.setMinimumHeight(140)
        form.addWidget(QLabel("YOUR PROMPT"))
        form.addWidget(self.prompt)
        self.negative = QLineEdit()
        self.negative.setPlaceholderText("Optional: things to avoid")
        form.addWidget(self.negative)
        self.lora_choice = QComboBox()
        self.lora_choice.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.lora_choice.setMinimumContentsLength(15)
        self.lora_choice.setItemDelegate(StatusDelegate(self.lora_choice))
        self.lora_choice.addItem("No LoRA", None)
        self.lora_strength = QDoubleSpinBox()
        self.lora_strength.setRange(0, 2)
        self.lora_strength.setSingleStep(0.1)
        self.lora_strength.setValue(1)
        self.lora_strength.setToolTip("0 disables the effect; 1 uses the trained strength.")
        fields = QFormLayout()
        self.size = QComboBox()
        for label, dimensions in [
            ("Square · 512 × 512", (512, 512)),
            ("Square · 768 × 768", (768, 768)),
            ("Square · 1024 × 1024", (1024, 1024)),
            ("Landscape · 1024 × 768", (1024, 768)),
            ("Portrait · 768 × 1024", (768, 1024)),
        ]:
            self.size.addItem(label, dimensions)
        self.steps = QSpinBox()
        self.steps.setRange(1, 100)
        self.guidance = QDoubleSpinBox()
        self.guidance.setRange(0, 20)
        self.guidance.setSingleStep(0.5)
        self.seed = QLineEdit("0")
        self.seed.setToolTip(
            "0 picks a fresh random seed each time. Use 1–4294967295 to repeat an image."
        )
        self.mode = QComboBox()
        self.mode.addItem("GPU · fastest", "gpu")
        self.mode.addItem("CPU offload · less VRAM", "offload")
        self.mode.addItem("Sequential offload · minimum VRAM", "minimal")
        for label, widget in [
            ("LoRA adapter", self.lora_choice),
            ("LoRA strength", self.lora_strength),
            ("Image size", self.size),
            ("Steps", self.steps),
            ("Guidance", self.guidance),
            ("Seed", self.seed),
            ("Memory", self.mode),
        ]:
            fields.addRow(label, widget)
        form.addLayout(fields)
        self.button("Load selected model", self.load_selected, form)
        create = self.button("✦  Create image", self.generate, form)
        create.setObjectName("primary")
        self.button("Unload model / free memory", self.unload, form)
        self.hint = QLabel("Images and prompts are saved automatically on this computer.")
        self.hint.setWordWrap(True)
        form.addWidget(self.hint)
        form.addStretch()
        right = QWidget()
        view = QVBoxLayout(right)
        self.preview = QLabel(
            "Your next idea starts here.\n\nChoose a model, write a prompt, create an image."
        )
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(300, 300)
        self.preview.setObjectName("preview")
        view.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        self.button("Save a copy…", self.save_copy, actions)
        self.button("Open image folder", self.open_outputs, actions)
        view.addLayout(actions)
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setSizes([440, 640])
        box.addWidget(splitter)
        self.tabs.addTab(tab, "Create")

    def models_tab(self):
        tab = QWidget()
        box = QVBoxLayout(tab)
        note = QLabel(
            "Start with a curated model or search Hugging Face. Full SD / SDXL Diffusers models "
            "are supported. Memory estimates assume one image at the default size."
        )
        note.setWordWrap(True)
        box.addWidget(note)
        legend = QLabel(
            "Green: likely fits  ·  Orange: tight memory / offload / base selection needed  ·  Red: insufficient memory or incompatible"
        )
        legend.setWordWrap(True)
        box.addWidget(legend)
        search = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search models, or enter owner/model to inspect a repository")
        self.query.returnPressed.connect(self.search)
        search.addWidget(self.query)
        self.search_kind = QComboBox()
        self.search_kind.addItem(type_icon("checkpoint"), "Checkpoints", "checkpoint")
        self.search_kind.addItem(type_icon("lora"), "LoRAs", "lora")
        search.addWidget(self.search_kind)
        self.button("Search Hugging Face", self.search, search)
        self.button("Curated models", self.curated, search)
        box.addLayout(search)
        self.compatible_only = QCheckBox("Show recommended models only")
        self.compatible_only.toggled.connect(self.populate_models)
        box.addWidget(self.compatible_only)
        self.model_list = QListWidget()
        self.model_list.setItemDelegate(StatusDelegate(self.model_list))
        self.model_list.setIconSize(QSize(32, 32))
        self.model_list.currentItemChanged.connect(self.model_details)
        box.addWidget(self.model_list, 1)
        self.details = QLabel("Select a model to see details.")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.details)
        actions = QHBoxLayout()
        self.button("Install selected model", self.install_selected, actions)
        self.button("View model card / license", self.open_card, actions)
        self.button("Refresh hardware", self.refresh, actions)
        self.button("Import LoRA file…", self.import_lora, actions)
        box.addLayout(actions)
        self.tabs.addTab(tab, "Explore models")

    def gallery_tab(self):
        tab = QWidget()
        box = QVBoxLayout(tab)
        box.addWidget(
            QLabel("Your saved images · select one to view it and restore its prompt/settings")
        )
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setMovement(QListView.Movement.Static)
        self.gallery.setIconSize(QSize(160, 160))
        self.gallery.setGridSize(QSize(250, 220))
        self.gallery.setSpacing(8)
        self.gallery.setWordWrap(True)
        self.gallery.currentItemChanged.connect(self.restore_image)
        box.addWidget(self.gallery, 1)
        self.button("Refresh gallery", self.refresh_gallery, box)
        self.tabs.addTab(tab, "Gallery")

    def refresh_hardware(self):
        self.hw = hardware()
        self.hardware_label.setText(
            f"{self.hw['gpu']}  ·  {self.hw['vram']:.1f} GB VRAM "
            f"({self.hw['free_vram']:.1f} free)  ·  {self.hw['ram']:.0f} GB RAM  ·  "
            f"{self.hw['disk']:.0f} GB disk free"
        )

    def refresh(self):
        self.refresh_hardware()
        current = self.model_choice.currentData()
        self.model_choice.blockSignals(True)
        self.model_choice.clear()
        for model in installed_models():
            if model.kind == "checkpoint":
                self.model_choice.addItem(type_icon("checkpoint"), model.name, model)
                index = self.model_choice.count() - 1
                status, reason = compatibility(model, self.hw)
                self.model_choice.setItemData(
                    index, QColor(COLORS[status]), Qt.ItemDataRole.ForegroundRole
                )
                self.model_choice.setItemData(index, reason, Qt.ItemDataRole.ToolTipRole)
        if current:
            for i in range(self.model_choice.count()):
                if self.model_choice.itemData(i).repo == current.repo:
                    self.model_choice.setCurrentIndex(i)
        self.model_choice.blockSignals(False)
        self.refresh_loras()
        self.preset()
        self.populate_models()
        self.refresh_gallery()

    def preset(self):
        model = self.model_choice.currentData()
        if not model:
            return
        if hasattr(self, "lora_choice"):
            self.refresh_loras()
            if hasattr(self, "model_list"):
                self.populate_models()
        self.steps.setMaximum(4 if model.turbo else 100)
        self.steps.setValue(model.steps)
        self.guidance.setValue(model.guidance)
        self.guidance.setEnabled(not model.turbo)
        self.negative.setEnabled(not model.turbo)
        self.size.setCurrentIndex(2 if model.resolution == 1024 else 0)
        self.hint.setText(
            "Turbo models use 1–4 steps and ignore negative prompt / guidance. "
            "512 × 512 is recommended."
            if model.turbo
            else "Images include the prompt, settings, and seed for reuse."
        )

    def refresh_loras(self):
        current = self.lora_choice.currentData()
        base = self.model_choice.currentData()
        self.lora_choice.clear()
        self.lora_choice.addItem("No LoRA", None)
        for lora in installed_models():
            if lora.kind != "lora":
                continue
            matches = bool(base and lora_matches(lora, base))
            self.lora_choice.addItem(
                type_icon("lora"), f"{lora.name} · {architecture(lora).upper()}", lora
            )
            index = self.lora_choice.count() - 1
            status, reason = compatibility(lora, self.hw, base)
            self.lora_choice.setItemData(
                index, QColor(COLORS.get(status, "#ffb45f")), Qt.ItemDataRole.ForegroundRole
            )
            self.lora_choice.setItemData(index, reason, Qt.ItemDataRole.ToolTipRole)
            self.lora_choice.model().item(index).setEnabled(matches)
            if current and matches and current.repo == lora.repo:
                self.lora_choice.setCurrentIndex(index)

    def lora_selection(self):
        lora = self.lora_choice.currentData()
        return (
            {
                "repo": lora.repo,
                "weight_name": lora.weight_name,
                "strength": self.lora_strength.value(),
            }
            if lora
            else None
        )

    def populate_models(self, *_):
        self.model_list.clear()
        installed = {m.repo for m in installed_models()}
        for model in self.models:
            if isinstance(model, SearchResult) and model.model:
                model = model.model
            if isinstance(model, SearchResult):
                if self.compatible_only.isChecked():
                    continue
                label = model.repo + "\n" + model.reason
                status = "marginal" if model.status in {"failed", "restricted"} else "incompatible"
                kind = model.kind
            else:
                status, description = compatibility(
                    model,
                    self.hw,
                    self.model_choice.currentData() if model.kind == "lora" else None,
                )
                if self.compatible_only.isChecked() and status != "recommended":
                    continue
                kind = model.kind
                label = f"{model.name} · {'LoRA' if kind == 'lora' else 'Checkpoint'}{' · Installed' if model.repo in installed else ''}\n{description}"
            item = QListWidgetItem(type_icon(kind), label)
            item.setForeground(QColor(COLORS.get(status, "#ff7777")))
            item.setData(Qt.ItemDataRole.UserRole, model)
            self.model_list.addItem(item)
        if self.model_list.count():
            self.model_list.setCurrentRow(0)

    def model_details(self, item, *_):
        if not item:
            self.details.setText(
                "No models shown. Turn off the recommendation filter to explore more."
            )
            return
        model = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(model, SearchResult) and model.kind == "lora":
            self.details.setText(
                f"{model.repo}\nLoRA · Base: {model.base_model or architecture(model) or 'choose before installing'}\n"
                f"File: {model.weight_name}\nLicense: {model.license}\nUse with a matching checkpoint in Create; add trigger words from the model card."
            )
            return
        self.details.setText(
            f"{model.repo}\n{model.reason}"
            if isinstance(model, SearchResult)
            else f"{model.repo}\n{model.resolution} px · {model.steps} steps · "
            f"License: {model.license}\nDownload size is checked before installation. "
            "Review the model card for its license and access requirements."
        )

    def selected(self):
        item = self.model_list.currentItem()
        if not item:
            raise ValueError("Select a model first.")
        return item.data(Qt.ItemDataRole.UserRole)

    def curated(self):
        self.models = list(CATALOG)
        self.populate_models()

    def search(self):
        if self.task:
            return
        query = self.query.text().strip()
        kind = self.search_kind.currentData()
        if not query:
            self.curated()
            return

        def searched(models):
            self.refresh_hardware()
            self.models = models
            self.populate_models()
            supported = sum(result.model is not None for result in models)
            self.status.setText(
                f"Found {len(models)} models · {supported} supported. Memory estimates use your available hardware."
            )

        self.start(
            lambda emit, cancelled: search_with_compatibility(query, emit, cancelled, kind),
            searched,
        )

    def install_selected(self):
        if self.task:
            return
        try:
            selection = self.selected()
        except ValueError as error:
            self.error(str(error))
            return
        if isinstance(selection, SearchResult):
            self.error(selection.reason)
            return
        if selection.kind == "lora":
            if len(selection.weight_files) > 1:
                weight, accepted = QInputDialog.getItem(
                    self,
                    "LoRA weights",
                    "Choose the adapter file to install:",
                    selection.weight_files,
                    selection.weight_files.index(selection.weight_name),
                    False,
                )
                if not accepted:
                    return
                selection = replace(selection, weight_name=weight)
            if not architecture(selection):
                arch = self.choose_lora_base()
                if not arch:
                    return
                selection = replace(
                    selection, architecture=arch, family="sdxl" if arch == "sdxl" else "sd"
                )
        self.start(
            lambda emit, cancelled: self.engine.install(selection, emit, cancelled),
            lambda _: self.refresh(),
        )

    def choose_lora_base(self):
        choices = {"SD 1.5": "sd15", "SD 2 / SD Turbo": "sd2", "SDXL": "sdxl"}
        label, accepted = QInputDialog.getItem(
            self,
            "LoRA training base",
            "Which architecture was this LoRA trained for?",
            list(choices),
            0,
            False,
        )
        return choices[label] if accepted else None

    def import_lora(self):
        if self.task:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import LoRA", "", "LoRA weights (*.safetensors)"
        )
        if not filename:
            return
        arch = self.choose_lora_base()
        if arch:
            self.start(
                lambda emit, cancelled: self.engine.import_lora(filename, arch, emit, cancelled),
                lambda _: self.refresh(),
            )

    def open_card(self):
        try:
            model = self.selected()
            repo = model.repo
            QDesktopServices.openUrl(QUrl("https://huggingface.co/" + repo))
        except ValueError as error:
            self.error(str(error))

    def generation_model(self):
        model = self.model_choice.currentData()
        if not model:
            self.tabs.setCurrentIndex(1)
            raise ValueError("Install a model in Explore models first.")
        return model

    def load_selected(self):
        if self.task:
            return
        try:
            model = self.generation_model()
            mode = self.mode.currentData()
            selection = self.lora_selection()
            self.start(
                lambda emit, cancelled: self.engine.load_with_lora(
                    model, mode, selection, emit, cancelled
                )
            )
        except ValueError as error:
            self.error(str(error))

    def generate(self):
        if self.task:
            return
        try:
            model = self.generation_model()
            seed = int(self.seed.text())
            if seed < 0 or seed > 2**32 - 1:
                raise ValueError("Seed must be an integer from 0 to 4294967295. Use 0 for random.")
            if not self.prompt.toPlainText().strip():
                raise ValueError("Type a prompt first.")
            width, height = self.size.currentData()
            settings = {
                "prompt": self.prompt.toPlainText(),
                "negative": self.negative.text(),
                "seed": seed,
                "width": width,
                "height": height,
                "steps": self.steps.value(),
                "guidance": self.guidance.value(),
                "mode": self.mode.currentData(),
                "lora": self.lora_selection(),
            }
            self.start(
                lambda emit, cancelled: self.engine.generate(model, settings, emit, cancelled),
                self.generated,
            )
        except ValueError as error:
            self.error(str(error))

    def unload(self):
        self.start(
            lambda emit, cancelled: self.engine.unload(),
            lambda _: self.status.setText("Model unloaded. GPU memory released."),
        )

    def start(self, function, success=None):
        if self.task:
            return
        self.task = Task(function)
        for control in self.controls:
            control.setEnabled(False)
        self.model_choice.setEnabled(False)
        self.lora_choice.setEnabled(False)
        self.lora_strength.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Working…")
        self.task.progress.connect(self.update_progress)
        if success:
            self.task.success.connect(success)
        self.task.failure.connect(self.error)
        self.task.finished.connect(self.task_finished)
        self.task.start()

    def task_finished(self):
        self.task.deleteLater()
        self.task = None
        for control in self.controls:
            control.setEnabled(True)
        self.model_choice.setEnabled(True)
        self.lora_choice.setEnabled(True)
        self.lora_strength.setEnabled(True)
        self.cancel.setEnabled(False)

    def cancel_task(self):
        if self.task:
            self.task.cancelled.set()
            self.status.setText("Cancelling after the current download file or generation step…")
            self.cancel.setEnabled(False)

    def update_progress(self, message, percent):
        self.status.setText(message)
        self.progress.setValue(percent)

    def error(self, message):
        self.status.setText(message)
        if "cancelled" not in message.lower():
            QMessageBox.warning(self, "Cachy Canvas", message)

    def generated(self, path):
        self.preview_path = Path(path)
        self.show_preview()
        self.refresh_gallery()

    def show_preview(self):
        if self.preview_path:
            pixmap = QPixmap(str(self.preview_path))
            self.preview.setPixmap(
                pixmap.scaled(
                    self.preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview"):
            self.show_preview()

    def refresh_gallery(self):
        self.gallery.blockSignals(True)
        self.gallery.clear()
        for path in sorted((data_dir() / "outputs").glob("*.png"), reverse=True):
            item = QListWidgetItem(path.name)
            reader = QImageReader(str(path))
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(
                    size.scaled(self.gallery.iconSize(), Qt.AspectRatioMode.KeepAspectRatio)
                )
            image = reader.read()
            if not image.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(image)))
            item.setToolTip(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.gallery.addItem(item)
        self.gallery.blockSignals(False)

    def restore_image(self, item, *_):
        if not item or self.task:
            return
        self.preview_path = Path(item.data(Qt.ItemDataRole.UserRole))
        try:
            meta = json.loads(self.preview_path.with_suffix(".json").read_text())
            for i in range(self.model_choice.count()):
                if self.model_choice.itemData(i).repo == meta.get("model"):
                    self.model_choice.setCurrentIndex(i)
            self.prompt.setPlainText(meta["prompt"])
            self.negative.setText(meta.get("negative", ""))
            self.seed.setText(str(meta["seed"]))
            self.lora_choice.setCurrentIndex(0)
            if meta.get("lora"):
                restored_lora = False
                for i in range(1, self.lora_choice.count()):
                    adapter = self.lora_choice.itemData(i)
                    if (
                        adapter.repo == meta["lora"]["repo"]
                        and adapter.weight_name
                        == meta["lora"].get("weight_name", adapter.weight_name)
                        and self.lora_choice.model().item(i).isEnabled()
                    ):
                        self.lora_choice.setCurrentIndex(i)
                        self.lora_strength.setValue(meta["lora"].get("strength", 1))
                        restored_lora = True
                        break
                if not restored_lora:
                    self.status.setText(
                        "This image's LoRA is missing or incompatible. Install its recorded adapter to reproduce it."
                    )
            self.steps.setValue(meta["steps"])
            self.guidance.setValue(meta["guidance"])
            index = self.size.findData((meta["width"], meta["height"]))
            if index >= 0:
                self.size.setCurrentIndex(index)
            index = self.mode.findData(meta.get("mode", "gpu"))
            if index >= 0:
                self.mode.setCurrentIndex(index)
        except (OSError, KeyError, ValueError):
            pass
        self.show_preview()
        self.tabs.setCurrentIndex(0)

    def save_copy(self):
        if not self.preview_path:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save image", self.preview_path.name, "PNG images (*.png)"
        )
        if filename:
            import shutil

            try:
                if Path(filename).resolve() != self.preview_path.resolve():
                    shutil.copy2(self.preview_path, filename)
            except OSError as error:
                self.error(str(error))

    def open_outputs(self):
        path = data_dir() / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.task:
            self.cancel_task()
            self.status.setText("Stopping the current operation. Close again once it finishes.")
            event.ignore()
        else:
            event.accept()


STYLE = """
QWidget { background:#151a28; color:#e4e9f5; font-size:14px; }
QLabel { background:transparent; }
QTabWidget::pane { border:1px solid #30394e; border-radius:10px; }
QTabBar::tab { padding:12px 25px; background:#1d2435; }
QTabBar::tab:selected { color:#7ee0c3; border-bottom:2px solid #7ee0c3; }
QPushButton { background:#29344a; border:1px solid #3a4863; padding:10px 15px; border-radius:7px; }
QPushButton:hover { background:#384660; }
QPushButton:disabled { color:#768197; background:#202638; }
QPushButton#primary { background:#7ee0c3; color:#102822; font-weight:600; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {
    background:#1d2435; border:1px solid #37435c; border-radius:6px; padding:8px; }
QListWidget::item { padding:12px; border-bottom:1px solid #30394e; }
QListWidget::item:selected { background:#304a50; }
QLabel#preview { background:#101521; border:1px solid #30394e; border-radius:10px; color:#8593ab; }
QProgressBar { border:1px solid #37435c; border-radius:5px; text-align:center; }
QProgressBar::chunk { background:#547e71; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Cachy Canvas")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(500, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
