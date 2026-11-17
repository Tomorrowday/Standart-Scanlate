# services/ocr_ops/__init__.py
# Пакет операций OCR: нормализация текста, маскирование соседей и распознавание области бабла

from services.ocr_ops.text_normalizer import normalize_ocr_japanese_text
from services.ocr_ops.neighbor_masking import _mask_foreign_neighbor_regions_in_page_coords
from services.ocr_ops.crop_edge_cleaner import _clean_ocr_crop_from_foreign_text
from services.ocr_ops.region_recognizer import (
    OCR_WHITE_BORDER,
    _int_crop_box,
    _recognize,
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
