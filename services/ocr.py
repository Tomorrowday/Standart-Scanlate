# services/ocr.py
"""
Каркас сервиса оптического распознавания японского текста (MangaOCR).
Реализация: services/ocr_impl.py
Зависимости реализации: PIL, cv2, numpy, math, re, torch, ml.models (ml, release_vram)
"""

from typing import Any, Dict, List, Optional

from PIL import Image
import services.ocr_impl as _impl


def normalize_ocr_japanese_text(text: str) -> str:
    """Нормализует японскую пунктуацию после распознавания."""
    return _impl.normalize_ocr_japanese_text(text)


def ocr_image_region(
    image: Image.Image,
    x: float,
    y: float,
    width: float,
    height: float,
    rotation: float = 0.0,
    class_id: int = 0,
    other_boxes: Optional[List[Dict[str, Any]]] = None,
    ocr_model_name: str = "manga-ocr-base",
) -> str:
    """
    Вырезает область бабла (с учетом поворота) и распознает японский текст через MangaOCR.
    Кроп вырезается строго по рамке бабла, белое поле добавляется уже после очистки,
    а пиксели соседних баблов (other_boxes) маскируются белым перед распознаванием.
    """
    return _impl.ocr_image_region(
        image, x, y, width, height, rotation, class_id, other_boxes, ocr_model_name
    )
