"""Adapter discovery, local storage, architecture checks, and pipeline state."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from core import (
    CATALOG,
    Model,
    architecture,
    compatibility,
    inspect_model,
    installed_models,
    lora_matches,
    model_path,
    save_model,
)
from engine import Cancelled, Engine, validate_lora_file
from safetensors.numpy import save_file


def write_adapter(path, arch="sd15"):
    dimension = {"sd15": 768, "sd2": 1024, "sdxl": 2048}[arch]
    save_file(
        {
            "unet.down_blocks.0.attentions.0.transformer_blocks.0.attn2.to_k.lora_A.weight": np.zeros(
                (2, dimension), dtype=np.float32
            ),
            "unet.down_blocks.0.attentions.0.transformer_blocks.0.attn2.to_k.lora_B.weight": np.zeros(
                (320, 2), dtype=np.float32
            ),
        },
        str(path),
    )


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict("os.environ", {"CACHY_CANVAS_DATA": self.directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def adapter(self, arch="sd15"):
        source = Path(self.directory.name) / "style.safetensors"
        write_adapter(source, arch)
        Engine().import_lora(source, arch, lambda *args: None, lambda: False)
        return installed_models()[0]

    def test_remote_lora_uses_its_base_architecture_and_safetensors_file(self):
        info = {
            "tags": ["lora"],
            "cardData": {"base_model": "runwayml/stable-diffusion-v1-5", "license": "openrail"},
            "siblings": [
                {"rfilename": "style.safetensors", "size": 1000000},
                {"rfilename": "unsafe.bin"},
            ],
        }
        with patch("core.api", return_value=info) as request:
            model = inspect_model("owner/style")
        self.assertEqual(model.kind, "lora")
        self.assertEqual(model.architecture, "sd15")
        self.assertEqual(model.weight_files, ["style.safetensors"])
        self.assertEqual(request.call_count, 1)

    def test_lora_does_not_fit_just_because_adapter_is_small(self):
        model = Model("owner/style", "style", "sdxl", 0, kind="lora", architecture="sdxl")
        hw = {"vram": 8, "free_vram": 7, "free_ram": 24}
        self.assertEqual(compatibility(model, hw)[0], "offload")
        self.assertEqual(compatibility(model, {**hw, "free_ram": 4})[0], "limited")
        self.assertEqual(compatibility(model, {**hw, "free_vram": 10.5})[0], "marginal")

    def test_sd15_lora_cannot_be_used_with_sd_turbo_or_sdxl(self):
        lora = self.adapter()
        self.assertTrue(lora_matches(lora, CATALOG[2]))
        self.assertFalse(lora_matches(lora, CATALOG[1]))
        self.assertFalse(lora_matches(lora, CATALOG[0]))
        self.assertEqual(architecture(CATALOG[1]), "sd2")

    def test_tensor_shapes_detect_wrong_architecture(self):
        source = Path(self.directory.name) / "style.safetensors"
        write_adapter(source, "sdxl")
        self.assertEqual(validate_lora_file(source), "sdxl")
        with self.assertRaisesRegex(ValueError, "selected base architecture"):
            Engine().import_lora(source, "sd15", lambda *args: None, lambda: False)
        self.assertEqual(installed_models(), [])

    def test_checkpoint_file_is_not_accepted_as_lora(self):
        source = Path(self.directory.name) / "checkpoint.safetensors"
        save_file({"unet.weight": np.zeros((2, 2), dtype=np.float32)}, str(source))
        with self.assertRaisesRegex(ValueError, "not a standard LoRA"):
            validate_lora_file(source, "sd15")

    def test_import_copies_weights_and_roundtrips_metadata(self):
        lora = self.adapter("sd2")
        self.assertTrue((model_path(lora) / lora.weight_name).is_file())
        self.assertEqual(lora.kind, "lora")
        self.assertEqual(lora.architecture, "sd2")
        self.assertGreater(lora.weight_bytes, 0)

    def test_cancelled_import_does_not_install(self):
        source = Path(self.directory.name) / "style.safetensors"
        write_adapter(source)
        with self.assertRaises(Cancelled):
            Engine().import_lora(source, "sd15", lambda *args: None, lambda: True)
        self.assertEqual(installed_models(), [])

    def test_adapter_weight_changes_do_not_reload_and_none_unloads(self):
        lora = self.adapter()
        engine = Engine()
        engine.pipe = Mock()
        pipe = engine.pipe
        selection = {"repo": lora.repo, "strength": 0.6}
        engine.apply_lora(CATALOG[2], selection, lambda *args: None, lambda: False)
        pipe.load_lora_weights.assert_called_once()
        pipe.set_adapters.assert_called_with(["canvas"], adapter_weights=[0.6])
        engine.apply_lora(
            CATALOG[2], {**selection, "strength": 1.2}, lambda *args: None, lambda: False
        )
        pipe.load_lora_weights.assert_called_once()
        pipe.set_adapters.assert_called_with(["canvas"], adapter_weights=[1.2])
        engine.apply_lora(CATALOG[2], None, lambda *args: None, lambda: False)
        pipe.unload_lora_weights.assert_called_once()
        self.assertIsNone(engine.active_lora)

    def test_incompatible_adapter_is_rejected_before_loading_weights(self):
        lora = self.adapter()
        engine = Engine()
        engine.pipe = Mock()
        with self.assertRaisesRegex(ValueError, "do not match"):
            engine.apply_lora(CATALOG[1], {"repo": lora.repo}, lambda *args: None, lambda: False)
        engine.pipe.load_lora_weights.assert_not_called()

    def test_failed_adapter_load_discards_partial_pipeline(self):
        lora = self.adapter()
        engine = Engine()
        engine.pipe = Mock()
        engine.pipe.load_lora_weights.side_effect = ValueError("invalid adapter")
        with (
            patch.object(engine, "unload") as unload,
            self.assertRaisesRegex(ValueError, "Could not apply"),
        ):
            engine.apply_lora(CATALOG[2], {"repo": lora.repo}, lambda *args: None, lambda: False)
        unload.assert_called_once()

    def test_download_marks_adapter_installed_after_validating_weights(self):
        model = Model(
            "owner/style",
            "style",
            "sd",
            0,
            kind="lora",
            architecture="sd15",
            weight_name="style.safetensors",
        )
        info = {"sha": "pinned", "siblings": [{"rfilename": model.weight_name, "size": 1}]}

        def download(repo, **kwargs):
            write_adapter(kwargs["local_dir"] / "style.safetensors")

        with (
            patch("engine.api", return_value=info),
            patch("engine.shutil.disk_usage", return_value=Mock(free=10 * 1024**3)),
            patch("huggingface_hub.snapshot_download", side_effect=download) as downloader,
        ):
            Engine().install(model, lambda *args: None, lambda: False)
        self.assertEqual(installed_models()[0].architecture, "sd15")
        self.assertEqual(downloader.call_args.kwargs["allow_patterns"], ["style.safetensors"])

    def test_adapter_manifest_cannot_escape_storage_directory(self):
        lora = replace(self.adapter(), weight_name="../../outside.safetensors")
        save_model(lora)
        self.assertEqual(installed_models(), [])


if __name__ == "__main__":
    unittest.main()
