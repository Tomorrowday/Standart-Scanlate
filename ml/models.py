# ml/models.py
"""
Менеджер ML-моделей (MangaOCR, YOLO, LaMa) и управление VRAM.
Публичный фасад пакета ml.models_ops.
Зависимости: torch, numpy, PIL, gc, logging, config
"""

from ml.models_ops import (
    AccurateLamaWrapper,
    BrushMaskWrapper,
    HayaiOcrAdapter,
    MLManager,
    PaddleOcrVlAdapter,
    _create_ocr_engine,
    _get_device,
    load_ml_models,
    ml,
    ml_manager,
    release_vram,
)
from ml.models_ops.transformers_compat import (
    _patch_tokenizer_config_if_needed,
    _patch_transformers_rope_compat,
)

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
    "_patch_tokenizer_config_if_needed",
    "_patch_transformers_rope_compat",
]
