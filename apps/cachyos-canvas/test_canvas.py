"""Tests without downloading multi-gigabyte weights or importing the ML runtime."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from core import (
    CATALOG,
    compatibility,
    download_files,
    inspect_model,
    inspect_search_result,
    installed_models,
    model_path,
    save_model,
    search_with_compatibility,
    validate_repo,
)


class ModelTests(unittest.TestCase):
    def test_search_inspects_results_and_preserves_search_order(self):
        with (
            patch(
                "core.search_models", return_value=["someone/xl", CATALOG[1].repo, "someone/flux"]
            ),
            patch(
                "core.inspect_model",
                side_effect=lambda repo: (
                    CATALOG[1]
                    if repo == CATALOG[1].repo
                    else CATALOG[0]
                    if repo == "someone/xl"
                    else self.reject_pipeline()
                ),
            ),
        ):
            results = search_with_compatibility("landscapes", lambda *args: None, lambda: False)
        self.assertEqual(
            [result.repo for result in results], ["someone/xl", CATALOG[1].repo, "someone/flux"]
        )
        self.assertEqual(
            [result.status for result in results], ["supported", "supported", "unsupported"]
        )
        self.assertEqual(
            compatibility(results[0].model, {"vram": 16, "free_vram": 4, "free_ram": 24})[0],
            "offload",
        )

    @staticmethod
    def reject_pipeline():
        raise ValueError("FLUX is unsupported")

    def test_model_access_and_network_errors_are_distinct(self):
        for error, status in [
            (
                HTTPError("https://huggingface.co/owner/model", 403, "Forbidden", {}, None),
                "restricted",
            ),
            (
                HTTPError("https://huggingface.co/owner/model", 404, "Not found", {}, None),
                "unsupported",
            ),
            (URLError("offline"), "failed"),
        ]:
            with self.subTest(status=status), patch("core.inspect_model", side_effect=error):
                result = inspect_search_result("owner/model")
                self.assertEqual(result.status, status)
                self.assertIsNone(result.model)
                self.assertTrue(result.reason)

    def test_cancelled_search_does_not_publish_partial_results(self):
        with (
            patch("core.inspect_model", return_value=CATALOG[0]),
            self.assertRaisesRegex(InterruptedError, "cancelled"),
        ):
            search_with_compatibility(CATALOG[0].repo, lambda *args: None, lambda: True)

    def test_download_uses_only_one_precision_and_no_pickle_or_code(self):
        names = [
            "model_index.json",
            "unet/config.json",
            "unet/diffusion_pytorch_model.safetensors",
            "unet/diffusion_pytorch_model.fp16.safetensors",
            "unet/model.bin",
            "text_encoder/model.safetensors",
            "tokenizer/vocab.json",
            "tokenizer/merges.txt",
            "model.safetensors",
            "pipeline.py",
            "onnx/model.onnx",
            "README.md",
        ]
        selected = download_files([{"rfilename": n} for n in names], "fp16")
        self.assertEqual(
            selected,
            sorted(
                [
                    "model_index.json",
                    "unet/config.json",
                    "unet/diffusion_pytorch_model.fp16.safetensors",
                    "text_encoder/model.safetensors",
                    "tokenizer/vocab.json",
                    "tokenizer/merges.txt",
                ]
            ),
        )

    def test_hardware_filter_uses_free_memory_and_reports_unknown(self):
        hw = {"vram": 16, "free_vram": 14, "free_ram": 24}
        self.assertEqual(compatibility(CATALOG[0], hw)[0], "recommended")
        hw["free_vram"] = 4
        self.assertEqual(compatibility(CATALOG[0], hw)[0], "offload")
        hw["vram"] = 0
        self.assertEqual(compatibility(CATALOG[0], hw)[0], "unavailable")

    def test_interrupted_download_is_not_installed(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"CACHY_CANVAS_DATA": directory}),
        ):
            path = model_path(CATALOG[0])
            path.mkdir(parents=True)
            (path / "model_index.json").write_text("{}")
            self.assertEqual(installed_models(), [])
            save_model(CATALOG[0])
            self.assertEqual(installed_models(), [CATALOG[0]])

    def test_repository_validation_blocks_path_traversal(self):
        for value in ("../../tmp", "https://host/model", "../model", "owner/..", "/tmp/a"):
            with self.assertRaises(ValueError):
                validate_repo(value)

    def test_search_inspection_rejects_other_pipeline_families(self):
        with (
            patch("core.api", return_value={"_class_name": "FluxPipeline"}),
            self.assertRaisesRegex(ValueError, "Supported models"),
        ):
            inspect_model("someone/flux")
        with patch(
            "core.api",
            side_effect=[
                {"cardData": {"license": "openrail"}},
                {"_class_name": "StableDiffusionXLPipeline"},
            ],
        ):
            model = inspect_model("someone/beautiful-xl")
            self.assertEqual(model.family, "sdxl")
            self.assertEqual(model.resolution, 1024)
            self.assertEqual(model.license, "openrail")

    def test_unrecognized_distilled_models_require_a_preset(self):
        with (
            patch("core.api", return_value={"_class_name": "StableDiffusionXLPipeline"}),
            self.assertRaisesRegex(ValueError, "specific preset"),
        ):
            inspect_model("someone/lightning-xl")


class GenerationTests(unittest.TestCase):
    def test_install_pins_revision_and_marks_only_complete_downloads(self):
        from engine import Engine
        from huggingface_hub import snapshot_download

        siblings = [
            {"rfilename": name, "size": 1}
            for name in ("model_index.json", "unet/diffusion_pytorch_model.fp16.safetensors")
        ]

        def download(repo, **kwargs):
            path = kwargs["local_dir"]
            for name in kwargs["allow_patterns"]:
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"_class_name": "StableDiffusionXLPipeline"}))

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"CACHY_CANVAS_DATA": directory}),
            patch("engine.api", return_value={"sha": "pinned-commit", "siblings": siblings}),
            patch(
                "engine.shutil.disk_usage", return_value=types.SimpleNamespace(free=10 * 1024**3)
            ),
            patch(
                "huggingface_hub.snapshot_download",
                autospec=snapshot_download,
                side_effect=download,
            ) as mocked,
        ):
            Engine().install(CATALOG[0], lambda *args: None, lambda: False)
            self.assertEqual(installed_models(), [CATALOG[0]])
            self.assertEqual(mocked.call_args.kwargs["revision"], "pinned-commit")
            self.assertNotIn("filename", mocked.call_args.kwargs)

    def test_failed_download_never_marks_model_installed(self):
        from engine import Engine

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"CACHY_CANVAS_DATA": directory}),
            patch(
                "engine.shutil.disk_usage", return_value=types.SimpleNamespace(free=10 * 1024**3)
            ),
            patch(
                "engine.api",
                return_value={
                    "sha": "pinned-commit",
                    "siblings": [
                        {"rfilename": "unet/diffusion_pytorch_model.safetensors", "size": 1}
                    ],
                },
            ),
            patch("huggingface_hub.snapshot_download", side_effect=OSError("connection lost")),
        ):
            with self.assertRaisesRegex(OSError, "connection lost"):
                Engine().install(CATALOG[0], lambda *args: None, lambda: False)
            self.assertEqual(installed_models(), [])

    def test_turbo_arguments_and_saved_seed(self):
        import sys
        import types

        from engine import Engine

        class Generator:
            def __init__(self, device):
                self.device = device

            def manual_seed(self, seed):
                self.seed = seed
                return self

        class Context:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class Image:
            def save(self, path, **kwargs):
                path.write_bytes(b"fake image")

        calls = []

        def pipeline(**kwargs):
            calls.append(kwargs)
            kwargs["callback_on_step_end"](None, 0, None, {})
            return types.SimpleNamespace(images=[Image()], nsfw_content_detected=None)

        torch = types.SimpleNamespace(
            Generator=Generator,
            inference_mode=Context,
            OutOfMemoryError=type("OOM", (Exception,), {}),
        )
        settings = {
            "prompt": "a forest",
            "negative": "blur",
            "steps": 1,
            "seed": 123,
            "width": 512,
            "height": 512,
            "guidance": 9,
            "mode": "gpu",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"CACHY_CANVAS_DATA": directory}),
            patch.dict(sys.modules, {"torch": torch}),
        ):
            engine = Engine()
            engine.pipe = pipeline
            with patch.object(engine, "load"):
                result = engine.generate(CATALOG[0], settings, lambda *args: None, lambda: False)
            self.assertTrue(Path(result).exists())
            meta = json.loads(Path(result).with_suffix(".json").read_text())
            self.assertEqual(meta["seed"], 123)
            self.assertEqual(calls[0]["guidance_scale"], 0)
            self.assertNotIn("negative_prompt", calls[0])
            settings["seed"] = 0
            with (
                patch.object(engine, "load"),
                patch("engine.secrets.randbelow", side_effect=[41, 98]),
            ):
                for expected in (42, 99):
                    result = engine.generate(
                        CATALOG[0], settings, lambda *args: None, lambda: False
                    )
                    meta = json.loads(Path(result).with_suffix(".json").read_text())
                    self.assertEqual(meta["seed"], expected)
                    self.assertEqual(calls[-1]["generator"].seed, expected)
            self.assertEqual(settings["seed"], 0)


if __name__ == "__main__":
    unittest.main()
