"""Exercise real PEFT adapter application/removal on the installed SD Turbo GPU pipeline."""

import os
import tempfile
from pathlib import Path

import numpy as np
from core import CATALOG, data_dir, installed_models, model_path
from engine import Engine
from PIL import Image
from safetensors.numpy import save_file


def main():
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("LoRA smoke test requires host CUDA.")
    base = CATALOG[1]
    original = model_path(base)
    if not original.exists():
        raise SystemExit("Install SD Turbo first. This test downloads no model weights.")
    state = Path(__file__).resolve().parents[2] / ".state"
    state.mkdir(exist_ok=True)
    previous = os.environ.get("CACHY_CANVAS_DATA")
    with tempfile.TemporaryDirectory(prefix="canvas-lora-test-", dir=state) as directory:
        os.environ["CACHY_CANVAS_DATA"] = directory
        models = data_dir() / "models"
        models.mkdir()
        model_path(base).symlink_to(original, target_is_directory=True)
        engine = Engine()

        def emit(message, percent):
            print(f"{percent:3}% {message}", flush=True)

        settings = {
            "prompt": "A mountain lake at sunset, watercolor painting",
            "negative": "",
            "width": 512,
            "height": 512,
            "seed": 42,
            "steps": 2,
            "guidance": 0,
            "mode": "gpu",
            "lora": None,
        }
        first = engine.generate(base, settings, emit, lambda: False)
        target, module = next(
            (name, item)
            for name, item in engine.pipe.unet.named_modules()
            if name.endswith("attn2.to_k") and isinstance(item, torch.nn.Linear)
        )
        random = np.random.default_rng(42)
        source = Path(directory) / "verification-adapter.safetensors"
        save_file(
            {
                f"unet.{target}.lora_A.weight": random.normal(
                    0, 0.1, (4, module.in_features)
                ).astype(np.float32),
                f"unet.{target}.lora_B.weight": random.normal(
                    0, 0.1, (module.out_features, 4)
                ).astype(np.float32),
            },
            str(source),
            metadata={"ss_base_model_version": "sd_v2"},
        )
        engine.import_lora(source, "sd2", emit, lambda: False)
        adapter = next(item for item in installed_models() if item.kind == "lora")
        settings["lora"] = {
            "repo": adapter.repo,
            "strength": 0.8,
            "weight_name": adapter.weight_name,
        }
        adapted = engine.generate(base, settings, emit, lambda: False)
        settings["lora"] = None
        restored = engine.generate(base, settings, emit, lambda: False)
        with Image.open(first) as image:
            baseline = np.array(image)
        with Image.open(adapted) as image:
            changed = np.array(image)
        with Image.open(restored) as image:
            unadapted = np.array(image)
        assert not np.array_equal(baseline, changed), "Adapter should change the image."
        assert np.array_equal(baseline, unadapted), (
            "Removing the adapter should restore baseline generation."
        )
        print(
            "PASS: real GPU adapter changed the output; removing it exactly restored the seeded baseline.",
            flush=True,
        )
        engine.unload()
    if previous is None:
        os.environ.pop("CACHY_CANVAS_DATA", None)
    else:
        os.environ["CACHY_CANVAS_DATA"] = previous


if __name__ == "__main__":
    main()
