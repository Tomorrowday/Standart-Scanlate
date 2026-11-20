# ml/models_ops/__init__.py
# Пакет операций менеджера ML-моделей: VRAM, LaMa, OCR-адаптеры и синглтон MLManager

from ml.models_ops.vram import _get_device, release_vram
from ml.models_ops.brush_wrapper import BrushMaskWrapper
from ml.models_ops.lama_wrapper import AccurateLamaWrapper
from ml.models_ops.ocr_adapters import (
    HayaiOcrAdapter,
    PaddleOcrVlAdapter,
    _create_ocr_engine,
)
from ml.models_ops.manager import MLManager, ml, ml_manager, load_ml_models

__all__ = [
    "_get_device",
    "release_vram",
    "AccurateLamaWrapper",
    "BrushMaskWrapper",
    "HayaiOcrAdapter",
    "PaddleOcrVlAdapter",
    "_create_ocr_engine",
    "MLManager",
    "ml",
    "ml_manager",
    "load_ml_models",
]
