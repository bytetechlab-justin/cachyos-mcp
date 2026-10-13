"""End-to-end validation: install SD Turbo and make a real local GPU image."""

import json

from core import CATALOG, hardware, installed_models
from engine import Engine


def main():
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("GPU smoke test requires working CUDA on the host.")
    model = CATALOG[1]
    engine = Engine()
    print(json.dumps(hardware(), indent=2), flush=True)

    def emit(message, percent):
        print(f"{percent:3}% {message}", flush=True)

    if model.repo not in {installed.repo for installed in installed_models()}:
        engine.install(model, emit, lambda: False)
    settings = {
        "prompt": "A tiny cozy cabin beside a mountain lake, warm sunset, watercolor illustration",
        "negative": "",
        "seed": 42,
        "width": 512,
        "height": 512,
        "steps": 2,
        "guidance": 0,
        "mode": "gpu",
    }
    path = engine.generate(model, settings, emit, lambda: False)
    print(f"OUTPUT={path}", flush=True)
    engine.unload()


if __name__ == "__main__":
    main()
