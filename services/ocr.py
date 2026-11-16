# services/ocr.py
"""
Сервис оптического распознавания японского текста (MangaOCR).
Зависимости: PIL, cv2, numpy, math, re, torch, ml.models (ml, release_vram)
"""

from typing import Any, Dict, List, Optional

from PIL import Image
from services.ocr_ops import (
    OCR_WHITE_BORDER,
    _clean_ocr_crop_from_foreign_text,
    _int_crop_box,
    _mask_foreign_neighbor_regions_in_page_coords,
    _recognize,
    normalize_ocr_japanese_text,
    ocr_image_region,
)

__all__ = [
    "normalize_ocr_japanese_text",
    "_mask_foreign_neighbor_regions_in_page_coords",
    "_clean_ocr_crop_from_foreign_text",
    "OCR_WHITE_BORDER",
    "_int_crop_box",
    "_recognize",
    "ocr_image_region",
]
