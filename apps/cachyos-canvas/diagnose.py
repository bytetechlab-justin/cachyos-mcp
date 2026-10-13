import json

from core import hardware

if __name__ == "__main__":
    print(json.dumps(hardware(), indent=2))
    import torch

    print(f"PyTorch {torch.__version__}, CUDA build {torch.version.cuda}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Architectures: {torch.cuda.get_arch_list()}")
        print(f"GPU computation: {(torch.ones(1, device='cuda') * 2).item()}")
