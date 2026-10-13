"""Long operations called only on a background thread."""

import gc
import hashlib
import json
import os
import secrets
import shutil
import time
from dataclasses import replace
from pathlib import Path

from core import (
    Model,
    api,
    architecture,
    base_architecture,
    data_dir,
    download_files,
    installed_models,
    lora_matches,
    model_path,
    save_model,
    validate_weight_name,
)


def validate_lora_file(path, expected=""):
    from safetensors import safe_open

    with safe_open(str(path), framework="numpy") as weights:
        keys = list(weights.keys())
        if not any(
            any(part in key for part in ("lora_A", "lora_B", "lora_down", "lora_up"))
            for key in keys
        ):
            raise ValueError(
                "This file is not a standard LoRA adapter. Choose safetensors LoRA weights."
            )
        metadata = weights.metadata() or {}
        detected = base_architecture(metadata.get("ss_base_model_version", ""))
        if not detected and metadata.get("ss_v2") == "True":
            detected = "sd2"
        if not detected and any(
            "lora_te2_" in key or key.startswith("text_encoder_2.") for key in keys
        ):
            detected = "sdxl"
        if not detected:
            for key in keys:
                if (
                    "attn2" in key
                    and ("to_k" in key or "to_v" in key)
                    and ("lora_A" in key or "lora_down" in key)
                ):
                    shape = weights.get_slice(key).get_shape()
                    if len(shape) >= 2:
                        detected = {768: "sd15", 1024: "sd2", 2048: "sdxl"}.get(shape[1], "")
                        if detected:
                            break
    if detected and expected and detected != expected:
        raise ValueError(
            f"LoRA weights are {detected}, but the selected base architecture is {expected}."
        )
    if not (detected or expected):
        raise ValueError(
            "Cannot identify the LoRA architecture. Select its training base when importing."
        )
    return detected or expected


class Cancelled(Exception):
    pass


class Engine:
    def __init__(self):
        self.pipe = None
        self.loaded = None
        self.device = None
        self.mode = None
        self.active_lora = None

    def unload(self):
        self.pipe = None
        self.loaded = None
        self.active_lora = None
        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def install(self, model, emit, cancelled):
        from huggingface_hub import snapshot_download
        from tqdm.auto import tqdm

        emit("Checking model files and disk space…", 0)
        info = api(f"api/models/{model.repo}", {"blobs": "true"})
        revision = info["sha"]
        if model.kind == "lora":
            validate_weight_name(model.weight_name)
        files = (
            [model.weight_name]
            if model.kind == "lora"
            else download_files(info["siblings"], model.variant)
        )
        if model.kind == "lora" and model.weight_name not in {
            item["rfilename"] for item in info["siblings"]
        }:
            raise ValueError("The selected LoRA file is no longer available in this repository.")
        sizes = {
            item["rfilename"]: item.get("size", (item.get("lfs") or {}).get("size", 0))
            for item in info["siblings"]
        }
        path = model_path(model)
        path.mkdir(parents=True, exist_ok=True)
        needed = sum(sizes.get(name, 0) for name in files)
        if shutil.disk_usage(path).free < needed + 1024**3:
            raise ValueError(f"Not enough disk space. Allow {needed / 1024**3 + 1:.1f} GB.")
        engine_cancelled = cancelled

        class DownloadProgress(tqdm):
            def update(self, n=1):
                if engine_cancelled():
                    raise Cancelled("Download cancelled. You can resume it later.")
                return super().update(n)

        for i, name in enumerate(files):
            if cancelled():
                raise Cancelled("Download cancelled. You can resume it later.")
            emit(f"Downloading {name} ({i + 1}/{len(files)})…", int(i * 100 / len(files)))
            snapshot_download(
                model.repo,
                allow_patterns=[name],
                revision=revision,
                local_dir=path,
                token=os.environ.get("HF_TOKEN"),
                tqdm_class=DownloadProgress,
            )
        if cancelled():
            raise Cancelled("Download cancelled.")
        if model.kind == "lora":
            arch = validate_lora_file(path / model.weight_name, architecture(model))
            model = replace(
                model,
                architecture=arch,
                family="sdxl" if arch == "sdxl" else "sd",
                weight_bytes=(path / model.weight_name).stat().st_size,
            )
        else:
            manifest = json.loads((path / "model_index.json").read_text())
            from core import SUPPORTED

            if SUPPORTED.get(manifest.get("_class_name")) != model.family:
                raise ValueError(
                    "The downloaded pipeline does not match the supported model family."
                )
        (path / "canvas-source.json").write_text(
            json.dumps({"repo": model.repo, "revision": revision})
        )
        save_model(model)  # Installed marker only after all files complete.
        emit("Model installed. Select it in Create.", 100)
        return str(path)

    def import_lora(self, source, arch, emit, cancelled):
        source = Path(source)
        if source.suffix.lower() != ".safetensors":
            raise ValueError("Import a .safetensors LoRA file.")
        arch = validate_lora_file(source, arch)
        emit("Importing LoRA…", 0)
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                if cancelled():
                    raise Cancelled("Import cancelled.")
                digest.update(chunk)
        model = Model(
            "local/" + digest.hexdigest()[:24],
            source.stem,
            "sdxl" if arch == "sdxl" else "sd",
            0,
            kind="lora",
            architecture=arch,
            weight_name="adapter.safetensors",
            weight_bytes=source.stat().st_size,
            license="See original model card",
        )
        path = model_path(model)
        path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path / model.weight_name)
        if cancelled():
            raise Cancelled("Import cancelled.")
        save_model(model)
        emit("LoRA imported. Select it in Create.", 100)
        return str(path)

    def apply_lora(self, model, selection, emit, cancelled):
        if not selection:
            if self.active_lora:
                self.pipe.unload_lora_weights()
                self.active_lora = None
            return
        lora = next(
            (
                item
                for item in installed_models()
                if item.kind == "lora" and item.repo == selection["repo"]
            ),
            None,
        )
        if not lora:
            raise ValueError("The selected LoRA is not installed. Install or import it first.")
        if selection.get("weight_name", lora.weight_name) != lora.weight_name:
            raise ValueError(
                "The saved LoRA file differs from the installed adapter. Reinstall the recorded file."
            )
        if not lora_matches(lora, model):
            raise ValueError(
                "LoRA and checkpoint base architectures do not match. Select a compatible LoRA."
            )
        strength = float(selection.get("strength", 1))
        if not 0 <= strength <= 2:
            raise ValueError("LoRA strength must be between 0 and 2.")
        if cancelled():
            raise Cancelled("Cancelled.")
        identity = (lora.repo, lora.weight_name)
        try:
            if self.active_lora != identity:
                if self.active_lora:
                    self.pipe.unload_lora_weights()
                self.active_lora = None
                emit(f"Applying LoRA · {lora.name}…", 0)
                validate_lora_file(model_path(lora) / lora.weight_name, architecture(model))
                self.pipe.load_lora_weights(
                    str(model_path(lora)),
                    weight_name=lora.weight_name,
                    adapter_name="canvas",
                    local_files_only=True,
                    use_safetensors=True,
                )
                self.active_lora = identity
            self.pipe.set_adapters(["canvas"], adapter_weights=[strength])
        except (ValueError, RuntimeError, KeyError, OSError, ImportError) as error:
            self.unload()  # A partially loaded adapter must never affect a later image.
            raise ValueError(f"Could not apply this LoRA: {error}") from error

    def load_with_lora(self, model, mode, selection, emit, cancelled):
        self.load(model, mode, emit, cancelled)
        self.apply_lora(model, selection, emit, cancelled)
        emit("Model and adapter ready." if selection else "Model ready.", 100)

    def load(self, model, mode, emit, cancelled):
        import torch
        from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline

        if model.kind != "checkpoint":
            raise ValueError("Select a checkpoint as the base model; LoRAs are adapters.")
        if self.loaded == model.repo and self.mode == mode:
            return
        self.unload()
        if cancelled():
            raise Cancelled("Cancelled.")
        if not (model_path(model) / "canvas-model.json").exists():
            raise ValueError("Install this model first.")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            major, minor = torch.cuda.get_device_capability()
            arch = f"sm_{major}{minor}"
            if major >= 10 and arch not in torch.cuda.get_arch_list():
                raise ValueError(
                    "This GPU requires a Blackwell-compatible PyTorch build. "
                    "Rerun install.sh for the CUDA 12.8 build."
                )
        emit(f"Loading {model.name} on {self.device.upper()}…", 0)
        cls = StableDiffusionXLPipeline if model.family == "sdxl" else StableDiffusionPipeline
        kwargs = {
            "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
            "use_safetensors": True,
            "local_files_only": True,
        }
        if model.variant:
            kwargs["variant"] = model.variant
        pipe = cls.from_pretrained(str(model_path(model)), **kwargs)
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        if self.device == "cuda" and mode == "offload":
            pipe.enable_model_cpu_offload()
        elif self.device == "cuda" and mode == "minimal":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.to(self.device)
        pipe.set_progress_bar_config(disable=True)
        if cancelled():
            del pipe
            self.unload()
            raise Cancelled("Cancelled.")
        self.pipe, self.loaded, self.mode = pipe, model.repo, mode
        emit("Model ready.", 100)

    def generate(self, model, settings, emit, cancelled):
        import torch
        from PIL.PngImagePlugin import PngInfo

        prompt = settings["prompt"].strip()
        if not prompt:
            raise ValueError("Type a prompt first.")
        self.load(model, settings["mode"], emit, cancelled)
        self.apply_lora(model, settings.get("lora"), emit, cancelled)
        seed = settings["seed"] if settings["seed"] > 0 else secrets.randbelow(2**32 - 1) + 1
        steps = settings["steps"]

        def callback(pipe, step, timestep, kwargs):
            if cancelled():
                raise Cancelled("Generation cancelled.")
            emit(f"Creating image · step {step + 1}/{steps}", int((step + 1) * 100 / steps))
            return kwargs

        arguments = {
            "prompt": prompt,
            "width": settings["width"],
            "height": settings["height"],
            "num_inference_steps": steps,
            "guidance_scale": 0 if model.turbo else settings["guidance"],
            "generator": torch.Generator(device="cpu").manual_seed(seed),
            "callback_on_step_end": callback,
        }
        if not model.turbo:
            arguments["negative_prompt"] = settings["negative"]
        emit("Creating image…", 0)
        start = time.monotonic()
        try:
            with torch.inference_mode():
                result = self.pipe(**arguments)
        except torch.OutOfMemoryError as error:
            self.unload()
            raise ValueError(
                "GPU memory is full. Choose CPU offload or a smaller image and retry."
            ) from error
        if cancelled():
            raise Cancelled("Generation cancelled.")
        if getattr(result, "nsfw_content_detected", None) and any(result.nsfw_content_detected):
            raise ValueError("The model's safety checker filtered the result. Try another prompt.")
        outputs = data_dir() / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        path = outputs / f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.png"
        metadata = {
            **settings,
            "seed": seed,
            "model": model.repo,
            "elapsed_seconds": round(time.monotonic() - start, 2),
        }
        png = PngInfo()
        png.add_text("cachy_canvas", json.dumps(metadata))
        result.images[0].save(path, pnginfo=png)
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
        emit(f"Saved image · seed {seed} · {metadata['elapsed_seconds']}s", 100)
        return str(path)
