# ml/models_ops/vram.py
# Определение устройства (CUDA/CPU) и освобождение видеопамяти PyTorch

import gc
from typing import Dict

import torch


def _get_device() -> torch.device:
    """Определяет доступное устройство (CUDA или CPU)."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def release_vram() -> dict:
    """Принудительно очищает кэш видеопамяти PyTorch и сборщик мусора."""
    vram_before = 0.0
    vram_after = 0.0

    if torch.cuda.is_available():
        vram_before = torch.cuda.memory_allocated() / (1024 * 1024)

    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        vram_after = torch.cuda.memory_allocated() / (1024 * 1024)

    freed = max(0.0, vram_before - vram_after)
    return {
        "vram_before_mb": round(vram_before, 1),
        "vram_after_mb": round(vram_after, 1),
        "freed_mb": round(freed, 1),
    }


__all__ = ["_get_device", "release_vram"]
