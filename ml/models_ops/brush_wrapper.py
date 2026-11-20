# ml/models_ops/brush_wrapper.py
# Потокобезопасная обёртка над TorchScript-моделью маски текста (U-Net, weights/brush)

import threading

import torch


class BrushMaskWrapper:
    """
    Обёртка над TorchScript-моделью U-Net (4 канала: RGB + box prior).

    Модель самодостаточна: нормализация ImageNet и sigmoid уже внутри графа.
    На вход подаётся `(1, 4, H, W)` float в `[0..1]` (H, W кратны 32), на выходе —
    `(1, 1, H, W)` вероятности мазка в `[0..1]`. Потокобезопасна через общий lock.
    """

    def __init__(self, model: torch.jit.ScriptModule, device: torch.device, lock: threading.Lock):
        self.model = model
        self.device = device
        self._lock = lock

    @torch.inference_mode()
    def predict(self, tensor: torch.Tensor) -> torch.Tensor:
        """Прогоняет тензор на устройстве модели и возвращает вероятности `(1, 1, H, W)`."""
        with self._lock:
            if tensor.device != self.device:
                tensor = tensor.to(self.device)
            return self.model(tensor)


__all__ = ["BrushMaskWrapper"]
