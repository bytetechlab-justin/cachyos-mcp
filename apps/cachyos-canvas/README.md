# Cachy Canvas

A native Qt desktop app for local text-to-image generation on CachyOS. Choose a model,
type a prompt, and create an image. No node graph, hosted inference, or browser server.

## Install and open

```bash
cd /home/justin/Projects/cachyos-mcp/apps/cachyos-canvas
bash install.sh
bash launch.sh
```

The installer requires `uv`, uses a private Python 3.12 environment, and installs the
CUDA 12.8 PyTorch build for the RTX 5080. It adds **Cachy Canvas** to the application menu.
It does not change the system Python or NVIDIA drivers. Dependencies need several GB
of disk space. Model weights are downloaded only when you click Install in the app.

Start with **Explore models → SDXL Turbo → Install selected model**. Then switch to
**Create**, type a prompt, and click **Create image**. Loading happens automatically
on the first generation; the Load button also lets you load ahead of time. The loaded
model stays in memory for subsequent prompts until you unload it or close the app.
Seed **0** chooses a fresh random seed for each image. Positive seeds repeat the
same starting noise; the actual seed is saved with each image for reuse.
Turbo presets use 1–4 steps, 512 × 512, and zero guidance; negative prompts are disabled.

## Model discovery and compatibility

The curated list includes SD Turbo, SDXL Turbo, Stable Diffusion 1.5, and SDXL 1.0.
Live Hugging Face search automatically inspects Diffusers text-to-image repositories
in the background. Supported results show a GPU memory estimate against your current
available hardware: likely fits, requires offload, or low available memory. Unsupported
pipelines and models requiring access are labeled with the reason. Network failures
are labeled separately and can be retried by searching again. The recommendation
filter also works on search results. Only metadata is fetched during search.
Enter an `owner/model` ID directly to inspect a particular repository.

Supported repositories contain full `StableDiffusionPipeline` or
`StableDiffusionXLPipeline` models in safetensors format. LoRAs, GGUF, FLUX, single-file
checkpoints, custom Python pipelines, and unrecognized distilled presets are outside
this first version. Arbitrary SD/SDXL finetunes can need additional settings and have
not been individually tested. Remote Python code and pickle weights are not downloaded.

The app reads live NVIDIA VRAM, available system RAM, and disk space. The recommendation
filter uses **free** VRAM and conservative estimates for batch size one at the preset
resolution. These are estimates, not benchmarked guarantees. Large resolutions and
other GPU applications can increase memory pressure. CPU offload and sequential
offload use RAM to reduce VRAM usage; they run more slowly. Without working CUDA,
generation falls back to CPU, which can take a long time.

Downloads select one precision and omit duplicate checkpoints, ONNX exports, and other
unused files. Repository revisions are pinned for each installation. Interrupted
downloads can resume; a model is listed as installed only after all selected files
have downloaded. Progress shows individual files; cancel takes effect on the next
download file or denoising step. Loading and network requests may take time to finish
before cancellation takes effect.

Gated models require accepting their terms on Hugging Face and running the app with
`HF_TOKEN` set to a read token. Tokens are read from the environment, never saved by the
app. The model-card button opens licensing/access information in your browser.

## Files and privacy

Models and images live under `~/.local/share/cachy-canvas` (or `$XDG_DATA_HOME/cachy-canvas`).
Set `CACHY_CANVAS_DATA` to override that location. Images include prompt/settings/seed
metadata in PNG text and an adjacent JSON file. The gallery shows thumbnail tiles with
filenames; selecting a tile restores these settings and opens the image in Create.
Save a copy preserves PNG metadata, so shared images also contain the prompt.

Generation is local and offline after installation. Search and installation connect
to Hugging Face and its download infrastructure. The app inherits any Hugging Face
library telemetry preferences. No inference API or subscription is needed; individual
model licenses still apply. Unload releases the current pipeline's GPU allocations.
To remove a model, close the app and remove its `models/owner--model` folder; the app
currently has no in-app deletion control.

## Diagnose and test

```bash
.venv/bin/python diagnose.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -p 'test_*.py'
QT_QPA_PLATFORM=offscreen .venv/bin/python app.py --smoke-test
```

The diagnostics command checks CUDA with a real GPU tensor operation. If it fails,
verify the host driver with `nvidia-smi`. Sandboxed development environments may not
have GPU access even when the host does. The launch script escapes Flatpak through
`flatpak-spawn --host` when available.

Validated on this workstation: NVIDIA RTX 5080 (16 GB), PyTorch 2.11.0+cu128,
Diffusers 0.39.0, Python 3.12.14, and Qt Essentials 6.12.0. The full SD Turbo
download/load/generate/save path produced a 512 × 512 image in 15.44 seconds
(two denoising steps, first generation; model loading excluded). Fourteen unit/UI tests,
the offscreen Qt startup check, and Ruff checks passed. Other catalog models have
presets from their model cards but have not been generated with on this machine yet.

References: [SDXL Turbo preset](https://huggingface.co/stabilityai/sdxl-turbo),
[SD Turbo preset](https://huggingface.co/stabilityai/sd-turbo),
[SDXL](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0),
[Diffusers memory offload](https://huggingface.co/docs/diffusers/optimization/memory),
[PyTorch installation](https://pytorch.org/get-started/locally/).
