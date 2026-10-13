"""Qt interactions with temporary images and mocked model metadata; no network."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import COLORS, Window
from core import CATALOG, Model, SearchResult, model_path, save_model
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPalette
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict("os.environ", {"CACHY_CANVAS_DATA": self.directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        hw = {
            "gpu": "Test RTX",
            "vram": 16,
            "free_vram": 14,
            "ram": 32,
            "free_ram": 24,
            "disk": 100,
        }
        probe = patch("app.hardware", return_value=hw)
        probe.start()
        self.addCleanup(probe.stop)
        self.window = Window()
        self.addCleanup(self.window.close)

    def test_gallery_thumbnail_keeps_filename_and_restores_prompt(self):
        folder = Path(self.directory.name) / "outputs"
        folder.mkdir()
        path = folder / "a-landscape-image.png"
        image = QImage(320, 160, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.green)
        self.assertTrue(image.save(str(path)))
        path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "prompt": "a forest",
                    "seed": 42,
                    "steps": 2,
                    "guidance": 0,
                    "width": 512,
                    "height": 512,
                }
            )
        )
        self.window.refresh_gallery()
        item = self.window.gallery.item(0)
        self.assertEqual(item.text(), path.name)
        self.assertFalse(item.icon().isNull())
        thumb = item.icon().pixmap(self.window.gallery.iconSize())
        self.assertEqual(thumb.width(), thumb.height() * 2)
        self.window.tabs.setCurrentIndex(2)
        self.window.gallery.setCurrentRow(0)
        self.assertEqual(self.window.preview_path, path)
        self.assertEqual(self.window.prompt.toPlainText(), "a forest")
        self.assertEqual(self.window.seed.text(), "42")
        self.assertEqual(self.window.tabs.currentIndex(), 0)

    def test_searched_models_show_hardware_estimates_and_filter(self):
        self.window.models = [
            SearchResult(CATALOG[0].repo, CATALOG[0], "supported"),
            SearchResult("owner/flux", reason="Not supported by this app: FLUX"),
        ]
        self.window.populate_models()
        self.assertIn("Likely fits GPU", self.window.model_list.item(0).text())
        self.assertIn("Not supported", self.window.model_list.item(1).text())
        self.assertNotIn("compatibility unknown", self.window.model_list.item(0).text())
        self.window.compatible_only.setChecked(True)
        self.assertEqual(self.window.model_list.count(), 1)
        self.window.hw["free_vram"] = 4
        self.window.populate_models()
        self.assertEqual(self.window.model_list.count(), 0)
        self.window.compatible_only.setChecked(False)
        self.assertIn("Needs memory offload", self.window.model_list.item(0).text())

    def test_names_keep_status_colors_when_selected_and_have_type_icons(self):
        self.window.models = [CATALOG[0]]
        for free, ram, status in [
            (14, 24, "recommended"),
            (8.5, 24, "marginal"),
            (4, 4, "limited"),
        ]:
            with self.subTest(status=status):
                self.window.hw.update(free_vram=free, free_ram=ram)
                self.window.populate_models()
                item = self.window.model_list.item(0)
                self.assertEqual(item.foreground().color().name(), COLORS[status])
                self.assertFalse(item.icon().isNull())
                option = QStyleOptionViewItem()
                self.window.model_list.itemDelegate().initStyleOption(
                    option, self.window.model_list.model().index(0, 0)
                )
                self.assertEqual(
                    option.palette.color(QPalette.ColorRole.HighlightedText).name(), COLORS[status]
                )

    def test_lora_picker_disables_wrong_base_architecture(self):
        for arch in ("sd2", "sd15"):
            adapter = Model(
                "local/" + arch,
                arch,
                "sd",
                0,
                kind="lora",
                architecture=arch,
                weight_name="adapter.safetensors",
            )
            path = model_path(adapter)
            path.mkdir(parents=True)
            (path / adapter.weight_name).write_bytes(b"placeholder")
            save_model(adapter)
        self.window.model_choice.addItem(CATALOG[1].name, CATALOG[1])
        self.window.refresh_loras()
        for i in range(1, self.window.lora_choice.count()):
            adapter = self.window.lora_choice.itemData(i)
            self.assertEqual(
                self.window.lora_choice.model().item(i).isEnabled(), adapter.architecture == "sd2"
            )
            self.assertFalse(self.window.lora_choice.itemIcon(i).isNull())


if __name__ == "__main__":
    unittest.main()
