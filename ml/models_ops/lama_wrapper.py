# ml/models_ops/lama_wrapper.py
# Потокобезопасная обёртка над TorchScript-моделью LaMa без ресайза (padding до кратности 8)

import threading
from typing import Dict

import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image


class AccurateLamaWrapper:
    """
    Обёртка над TorchScript-моделью LaMa.
    Использует дополнение (padding) без ресайза до кратности 8, что исключает замыливание арта манги.
    Потокобезопасна при параллельных запросах.
    """

    def __init__(self, model: torch.jit.ScriptModule, device: torch.device, lock: threading.Lock):
        self.model = model
        self.device = device
        self._lock = lock

    @torch.inference_mode()
    def __call__(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        orig_w, orig_h = image.size
        pad_w = (8 - orig_w % 8) % 8
        pad_h = (8 - orig_h % 8) % 8

        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        mask_np = np.array(mask.convert("L")).astype(np.float32)
        mask_np = (mask_np > 127).astype(np.float32)

        with self._lock:
            img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(self.device)
            mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(self.device)

            if pad_w > 0 or pad_h > 0:
                pad_mode = "reflect" if (pad_w < orig_w and pad_h < orig_h) else "replicate"
                img_tensor = F.pad(img_tensor, (0, pad_w, 0, pad_h), mode=pad_mode)
                mask_tensor = F.pad(mask_tensor, (0, pad_w, 0, pad_h), mode=pad_mode)

            try:
                out_tensor = self.model(img_tensor, mask_tensor)
                out_tensor = out_tensor[:, :, :orig_h, :orig_w]
                out_np = torch.clamp(out_tensor[0], 0, 1).permute(1, 2, 0).detach().cpu().float().numpy()
                out_uint8 = (out_np * 255.0).round().astype(np.uint8)
            finally:
                del img_tensor, mask_tensor
                if "out_tensor" in locals():
                    del out_tensor

        return Image.fromarray(out_uint8)


__all__ = ["AccurateLamaWrapper"]
