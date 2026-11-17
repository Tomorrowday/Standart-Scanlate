# services/detector.py
"""
Сервис детекции речевых баблов и текста (YOLO) и определения порядка чтения манги.
Зависимости: cv2, numpy, PIL, torch, ml.models (ml), logger
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image
from services.detector_ops import (
    detect_and_filter_bubbles,
    expand_box_to_bubble,
    find_text_core_bbox,
    resolve_overlapping_bubbles,
    sort_manga_reading_order,
)

__all__ = [
    "sort_manga_reading_order",
    "expand_box_to_bubble",
    "resolve_overlapping_bubbles",
    "find_text_core_bbox",
    "detect_and_filter_bubbles",
]