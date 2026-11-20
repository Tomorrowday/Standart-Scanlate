# services/cleaner.py
"""
Сервис очистки баблов (White Clean + LaMa Inpainting).
Зависимости: os, math, pathlib, cv2, numpy, PIL, torch, ml.models, config, database, logger
"""

from typing import Tuple
import numpy as np
from services.cleaner_ops import (
    _blend_rotated_patch,
    _build_bubble_interior_mask,
    _create_shape_mask,
    _get_affine_points,
    blend_inpainted_patch,
    build_text_stroke_mask,
    clean_speech_bubble,
    clean_white_bubble_patch,
    get_box_geometry,
    inpaint_by_brush_mask,
    inpaint_patch_with_lama,
    is_mostly_white_bubble,
    is_patch_monochrome,
    load_image_cv2,
    save_image_cv2,
    spot_clean_region,
)

__all__ = [
    "load_image_cv2",
    "save_image_cv2",
    "is_patch_monochrome",
    "get_box_geometry",
    "is_mostly_white_bubble",
    "_create_shape_mask",
    "_build_bubble_interior_mask",
    "clean_white_bubble_patch",
    "inpaint_patch_with_lama",
    "blend_inpainted_patch",
    "_get_affine_points",
    "_blend_rotated_patch",
    "build_text_stroke_mask",
    "clean_speech_bubble",
    "spot_clean_region",
    "inpaint_by_brush_mask",
]

# Реэкспорт утилиты очистки памяти для обратной совместимости
from ml.models import release_vram  # noqa: F401