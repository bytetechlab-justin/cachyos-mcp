"""Model metadata, storage, and hardware. No ML or GUI imports at startup."""

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPPORTED = {"StableDiffusionPipeline": "sd", "StableDiffusionXLPipeline": "sdxl"}


def data_dir():
    return Path(
        os.environ.get(
            "CACHY_CANVAS_DATA",
            str(
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "cachy-canvas"
            ),
        )
    )


@dataclass
class Model:
    repo: str
    name: str
    family: str
    vram: int
    resolution: int = 512
    steps: int = 25
    guidance: float = 7.0
    turbo: bool = False
    variant: str | None = None
    license: str = "See model card"
    kind: str = "checkpoint"
    architecture: str = ""
    base_model: str = ""
    weight_name: str = ""
    weight_bytes: int = 0
    weight_files: list[str] = field(default_factory=list)


CATALOG = [
    Model(
        "stabilityai/sdxl-turbo",
        "SDXL Turbo · quick images",
        "sdxl",
        8,
        steps=4,
        guidance=0,
        turbo=True,
        variant="fp16",
        license="sai-nc-community",
    ),
    Model(
        "stabilityai/sd-turbo",
        "SD Turbo · smallest starter",
        "sd",
        4,
        steps=4,
        guidance=0,
        turbo=True,
        variant="fp16",
        license="sai-nc-community",
    ),
    Model(
        "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "Stable Diffusion 1.5",
        "sd",
        4,
        license="creativeml-openrail-m",
    ),
    Model(
        "stabilityai/stable-diffusion-xl-base-1.0",
        "SDXL 1.0 · detailed images",
        "sdxl",
        10,
        resolution=1024,
        steps=30,
        guidance=5,
        variant="fp16",
        license="creativeml-openrail++-m",
    ),
]


def architecture(model):
    if model.architecture:
        return model.architecture
    if model.family == "sdxl":
        return "sdxl"
    if model.repo == "stabilityai/sd-turbo":
        return "sd2"
    if model.repo == "stable-diffusion-v1-5/stable-diffusion-v1-5":
        return "sd15"
    if model.kind == "checkpoint" and model.family == "sd":
        try:
            config = json.loads((model_path(model) / "unet/config.json").read_text())
            return {768: "sd15", 1024: "sd2"}.get(config.get("cross_attention_dim"), "")
        except (OSError, ValueError):
            pass
    return ""


def lora_matches(lora, base):
    return bool(architecture(lora) and architecture(lora) == architecture(base))


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def hardware():
    raw = run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]
    )
    gpu, total, free = "No usable NVIDIA GPU detected", 0, 0
    if raw:
        parts = raw.splitlines()[0].rsplit(",", 2)
        if len(parts) == 3:
            try:
                gpu, total, free = parts[0].strip(), int(parts[1]) / 1024, int(parts[2]) / 1024
            except ValueError:
                pass
    if not total:
        pci = run(["lspci"])
        names = [
            line.split(": ", 1)[-1]
            for line in pci.splitlines()
            if "VGA" in line or "3D controller" in line
        ]
        if names:
            gpu = names[0] + " (GPU runtime unavailable)"
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0]) / 1024**2
    except (OSError, ValueError):
        pass
    root = data_dir()
    while not root.exists():
        root = root.parent
    return {
        "gpu": gpu,
        "vram": total,
        "free_vram": free,
        "ram": mem.get("MemTotal", 0),
        "free_ram": mem.get("MemAvailable", 0),
        "disk": shutil.disk_usage(root).free / 1024**3,
    }


def compatibility(model, hw, base=None):
    # Estimates for batch=1 at the model's default resolution, not guarantees.
    estimate = model.vram
    suffix = ""
    if model.kind == "lora":
        if base and not lora_matches(model, base):
            return "incompatible", "LoRA base architecture does not match the selected checkpoint"
        if not architecture(model):
            return "marginal", "LoRA requires a base architecture before use"
        estimate = base.vram if base else {"sd15": 4, "sd2": 6, "sdxl": 10}[architecture(model)]
        estimate += max(0.25, model.weight_bytes / 1024**3 * 1.5)
        suffix = " including base checkpoint; adapter compatibility depends on training"
    if not hw["vram"]:
        return "unavailable", "GPU runtime unavailable; CPU generation is very slow"
    if hw["free_vram"] > estimate + 1:
        return "recommended", f"Likely fits GPU · estimated {estimate:g} GB VRAM{suffix}"
    if hw["free_vram"] >= estimate:
        return "marginal", f"Fits with little headroom · estimated {estimate:g} GB VRAM{suffix}"
    if hw["free_ram"] >= 16 and hw["free_vram"] >= 3:
        return "offload", f"Needs memory offload · estimated {estimate:g} GB VRAM{suffix}"
    return "limited", f"Low available memory · estimated {estimate:g} GB VRAM{suffix}"


def api(path, params=None):
    url = "https://huggingface.co/" + path
    if params:
        url += "?" + urlencode(params)
    headers = {"User-Agent": "CachyCanvas/0.1"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def validate_repo(repo):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or ".." in repo:
        raise ValueError("Use a Hugging Face repository ID such as stabilityai/sdxl-turbo.")
    return repo


def inspect_model(repo):
    validate_repo(repo)
    known = next((model for model in CATALOG if model.repo == repo), None)
    if known:
        return known
    info = api(f"api/models/{repo}")
    card = info.get("cardData") or {}
    tags = info.get("tags") or []
    filenames = [item["rfilename"] for item in info.get("siblings", [])]
    if (
        "lora" in tags
        or "peft" in tags
        or card.get("base_model_relation") == "adapter"
        or any("lora" in name.lower() and name.endswith(".safetensors") for name in filenames)
    ):
        return inspect_lora(repo, info)
    manifest = api(f"{repo}/resolve/main/model_index.json")
    family = SUPPORTED.get(manifest.get("_class_name"))
    if not family:
        raise ValueError(
            "Supported models are full Diffusers SD or SDXL text-to-image pipelines. "
            "FLUX, GGUF and single-file checkpoints are not supported yet."
        )
    # Unknown distilled pipelines can require different samplers/settings.
    if any(word in repo.lower() for word in ("turbo", "lightning", "lcm", "hyper")):
        raise ValueError("This distilled model needs a specific preset. Use a curated Turbo model.")
    arch = "sdxl" if family == "sdxl" else ""
    if family == "sd":
        config = api(f"{repo}/resolve/main/unet/config.json")
        arch = {768: "sd15", 1024: "sd2"}.get(config.get("cross_attention_dim"), "")
    return Model(
        repo,
        repo.split("/")[-1],
        family,
        10 if family == "sdxl" else 4,
        resolution=1024 if family == "sdxl" else 512,
        license=str(card.get("license", "See model card")),
        architecture=arch,
    )


class UnsupportedLora(ValueError):
    pass


def inspect_lora(repo, info):
    card = info.get("cardData") or {}
    base = card.get("base_model", "")
    if isinstance(base, list):
        base = base[0] if base else ""
    if not isinstance(base, str):
        base = ""
    arch = base_architecture(base)
    if not arch and base:
        try:
            validate_repo(base)
            manifest = api(f"{base}/resolve/main/model_index.json")
            if manifest.get("_class_name") == "StableDiffusionXLPipeline":
                arch = "sdxl"
            elif manifest.get("_class_name") == "StableDiffusionPipeline":
                config = api(f"{base}/resolve/main/unet/config.json")
                arch = {768: "sd15", 1024: "sd2"}.get(config.get("cross_attention_dim"), "")
        except (HTTPError, URLError, ValueError, TimeoutError):
            pass
    if base and not arch:
        raise UnsupportedLora("This LoRA's base model is unsupported or could not be identified.")
    siblings = info.get("siblings", [])
    weights = [
        item["rfilename"]
        for item in siblings
        if item["rfilename"].endswith(".safetensors")
        and item["rfilename"].split("/")[0] not in {"unet", "vae", "text_encoder", "text_encoder_2"}
    ]
    if not weights:
        raise UnsupportedLora("No safetensors LoRA weights found.")
    # Diffusers can load standard LoRA/Kohya adapters; distilled adapters need sampler presets.
    if any(word in repo.lower() for word in ("lightning", "lcm", "hyper")):
        raise UnsupportedLora(
            "This acceleration LoRA requires a sampler preset that is not supported yet."
        )
    weight = next(
        (name for name in weights if name == "pytorch_lora_weights.safetensors"), weights[0]
    )
    for name in weights:
        validate_weight_name(name)
    size = max(
        (
            item.get("size", 0) or (item.get("lfs") or {}).get("size", 0)
            for item in siblings
            if item["rfilename"] in weights
        ),
        default=0,
    )
    return Model(
        repo,
        repo.split("/")[-1],
        "sdxl" if arch == "sdxl" else "sd",
        0,
        kind="lora",
        architecture=arch,
        base_model=base,
        weight_name=weight,
        weight_files=weights,
        weight_bytes=size,
        license=str(card.get("license", "See model card")),
    )


def base_architecture(base):
    name = base.lower()
    if "sdxl" in name or "stable-diffusion-xl" in name:
        return "sdxl"
    if "stable-diffusion-v1" in name or "stable-diffusion-1" in name or name in {"sd_v1", "sd15"}:
        return "sd15"
    if "stable-diffusion-2" in name or name in {"sd_v2", "sd2"} or base == "stabilityai/sd-turbo":
        return "sd2"
    return ""


def validate_weight_name(name):
    path = Path(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or not name.endswith(".safetensors")
    ):
        raise ValueError(
            "LoRA weights must be a relative .safetensors path inside the model folder."
        )
    return name


def search_models(query, kind="checkpoint"):
    entries = api(
        "api/models",
        {
            "search": query,
            "filter": "lora" if kind == "lora" else "diffusers",
            "pipeline_tag": "text-to-image",
            "sort": "downloads",
            "direction": -1,
            "limit": 20,
        },
    )
    return [entry["id"] for entry in entries]


@dataclass
class SearchResult:
    repo: str
    model: Model | None = None
    status: str = "unsupported"
    reason: str = ""
    kind: str = "checkpoint"


def inspect_search_result(repo):
    try:
        model = inspect_model(repo)
        return SearchResult(repo, model=model, status="supported", kind=model.kind)
    except UnsupportedLora as error:
        return SearchResult(repo, reason="Not supported by this app: " + str(error), kind="lora")
    except HTTPError as error:
        if error.code in (401, 403):
            return SearchResult(
                repo,
                status="restricted",
                reason="Access required: review the model card and Hugging Face token.",
            )
        if error.code == 404:
            return SearchResult(
                repo, reason="No full Diffusers pipeline found; not supported by this app."
            )
        return SearchResult(
            repo,
            status="failed",
            reason=f"Metadata request failed (HTTP {error.code}); retry search.",
        )
    except json.JSONDecodeError:
        return SearchResult(repo, status="failed", reason="Invalid model metadata; retry search.")
    except ValueError as error:
        return SearchResult(repo, reason="Not supported by this app: " + str(error))
    except (URLError, TimeoutError, OSError):
        return SearchResult(
            repo, status="failed", reason="Could not reach model metadata; retry search."
        )


def search_with_compatibility(query, emit, cancelled, kind="checkpoint"):
    """Inspect small metadata files concurrently; never download model weights."""
    emit("Searching Hugging Face…", 0)
    repos = [query] if "/" in query and " " not in query else search_models(query, kind)
    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = {executor.submit(inspect_search_result, repo): repo for repo in repos}
        for future in as_completed(pending):
            if cancelled():
                for task in pending:
                    task.cancel()
                raise InterruptedError("Search cancelled.")
            repo = pending[future]
            result = future.result()
            if result.model is None and kind == "lora":
                result.kind = "lora"
            results[repo] = result
            emit(
                f"Checking model support and memory estimates · {len(results)}/{len(repos)}",
                int(len(results) * 100 / max(len(repos), 1)),
            )
    if cancelled():
        raise InterruptedError("Search cancelled.")
    return [results[repo] for repo in repos]


def model_path(model):
    validate_repo(model.repo)
    return data_dir() / "models" / model.repo.replace("/", "--")


def installed_models():
    models = []
    for path in sorted((data_dir() / "models").glob("*/canvas-model.json")):
        try:
            model = Model(**json.loads(path.read_text()))
            if model.kind == "lora":
                validate_weight_name(model.weight_name)
            complete = (
                (path.parent / model.weight_name).is_file()
                if model.kind == "lora"
                else (path.parent / "model_index.json").exists()
            )
            if path.parent == model_path(model) and complete:
                models.append(model)
        except (OSError, ValueError, TypeError):
            continue
    return models


def download_files(siblings, variant):
    """Select safetensors only, one precision, and pipeline/tokenizer config."""
    files = [item["rfilename"] for item in siblings]
    weights = [
        name
        for name in files
        if name.endswith(".safetensors")
        and "/" in name
        and name.split("/", 1)[0]
        in {"unet", "vae", "text_encoder", "text_encoder_2", "safety_checker"}
    ]
    selected = []
    for component in {name.split("/")[0] for name in weights}:
        group = [name for name in weights if name.startswith(component + "/")]
        half = [name for name in group if ".fp16." in name]
        selected += (
            half
            if variant == "fp16" and half
            else [name for name in group if not any(p in name for p in (".fp16.", ".bf16."))]
        )
    if not selected:
        raise ValueError("No supported safetensors pipeline weights found.")
    components = {
        "scheduler",
        "tokenizer",
        "tokenizer_2",
        "unet",
        "vae",
        "text_encoder",
        "text_encoder_2",
        "safety_checker",
        "feature_extractor",
    }
    for name in files:
        if name == "model_index.json" or (
            name.split("/")[0] in components and name.endswith((".json", ".txt", ".model"))
        ):
            selected.append(name)
    return sorted(set(selected))


def save_model(model):
    (model_path(model) / "canvas-model.json").write_text(json.dumps(asdict(model), indent=2))
