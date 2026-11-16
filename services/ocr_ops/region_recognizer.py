# services/ocr_ops/region_recognizer.py
# Вырезание области бабла (с поворотом) и распознавание через выбранную OCR-модель

import math
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
import torch
from ml.models import ml
from services.ocr_ops.crop_edge_cleaner import _clean_ocr_crop_from_foreign_text
from services.ocr_ops.neighbor_masking import _mask_foreign_neighbor_regions_in_page_coords
from services.ocr_ops.text_normalizer import normalize_ocr_japanese_text

# Белое поле, которое добавляется вокруг уже вырезанного и очищенного кропа.
# Оно нужно MangaOCR для комфортного распознавания, но НЕ захватывает пиксели соседних баблов.
OCR_WHITE_BORDER = 12


def _int_crop_box(
    cx: float,
    cy: float,
    bw: int,
    bh: int,
    img_w: int,
    img_h: int,
    outward_pad: int,
) -> Tuple[int, int, int, int]:
    """Возвращает целочисленную рамку кропа вокруг центра бабла (с минимальным внешним паддингом)."""
    x1 = max(0, int(cx - bw / 2.0) - outward_pad)
    y1 = max(0, int(cy - bh / 2.0) - outward_pad)
    x2 = min(img_w, int(cx + bw / 2.0) + outward_pad)
    y2 = min(img_h, int(cy + bh / 2.0) + outward_pad)
    return x1, y1, x2, y2


def _recognize(crop_img: Image.Image, ocr_model_name: str = "manga-ocr-base") -> str:
    """Отправляет подготовленный кроп в выбранную OCR-модель под блокировкой MLManager."""
    ocr_instance = ml.get_ocr(ocr_model_name)
    with ml.lock, torch.inference_mode():
        raw_text = ocr_instance(crop_img).strip()
    return normalize_ocr_japanese_text(raw_text)


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
    Вырезает область бабла и распознает через MangaOCR.
    Выполняется под блокировкой MLManager для безопасности при параллельных запросах.
    """
    img_w, img_h = image.size

    cx = (x + width / 2.0) * img_w
    cy = (y + height / 2.0) * img_h
    bw = max(2, int(width * img_w))
    bh = max(2, int(height * img_h))

    outward_pad = 2 if class_id in (2, 3) else 0
    target_box_px = _int_crop_box(cx, cy, bw, bh, img_w, img_h, outward_pad)

    # 1. Прямой кроп
    if abs(rotation) < 0.5:
        x1, y1, x2, y2 = target_box_px
        if x2 <= x1 or y2 <= y1:
            return ""

        crop_img = image.crop((x1, y1, x2, y2))
        crop_img = _clean_ocr_crop_from_foreign_text(
            crop_img, (x1, y1, x2, y2), (img_w, img_h), class_id, other_boxes
        )
        crop_img = ImageOps.expand(crop_img, border=OCR_WHITE_BORDER, fill=(255, 255, 255))
        return _recognize(crop_img, ocr_model_name=ocr_model_name)

    # 2. Повернутый кроп
    radius = math.ceil(math.sqrt(bw * bw + bh * bh) / 2.0) + outward_pad + 4
    sub_x1 = max(0, int(cx - radius))
    sub_y1 = max(0, int(cy - radius))
    sub_x2 = min(img_w, int(cx + radius))
    sub_y2 = min(img_h, int(cy + radius))

    if sub_x2 <= sub_x1 or sub_y2 <= sub_y1:
        return ""

    sub_crop = image.crop((sub_x1, sub_y1, sub_x2, sub_y2))

    # Маскируем соседние баблы ещё в глобальных координатах страницы до поворота sub_crop
    if class_id in (0, 1) and other_boxes:
        sub_arr = np.array(sub_crop.convert("RGB"))
        gray_sub = cv2.cvtColor(sub_arr, cv2.COLOR_RGB2GRAY)
        if float(np.mean(gray_sub > 195)) >= 0.45:
            _mask_foreign_neighbor_regions_in_page_coords(
                arr=sub_arr,
                arr_box_px=(sub_x1, sub_y1, sub_x2, sub_y2),
                target_box_px=target_box_px,
                img_size=(img_w, img_h),
                other_boxes=other_boxes,
            )
            sub_crop = Image.fromarray(sub_arr)

    local_cx = cx - sub_x1
    local_cy = cy - sub_y1

    rotated_sub = sub_crop.rotate(
        rotation,
        resample=Image.Resampling.BICUBIC,
        center=(local_cx, local_cy),
        fillcolor=(255, 255, 255)
    )

    rx1 = max(0, int(local_cx - bw / 2.0) - outward_pad)
    ry1 = max(0, int(local_cy - bh / 2.0) - outward_pad)
    rx2 = min(rotated_sub.width, int(local_cx + bw / 2.0) + outward_pad)
    ry2 = min(rotated_sub.height, int(local_cy + bh / 2.0) + outward_pad)

    if rx2 <= rx1 or ry2 <= ry1:
        return ""

    final_crop = rotated_sub.crop((rx1, ry1, rx2, ry2))
    final_crop = _clean_ocr_crop_from_foreign_text(
        final_crop, (rx1, ry1, rx2, ry2), (rotated_sub.width, rotated_sub.height), class_id, None
    )
    final_crop = ImageOps.expand(final_crop, border=OCR_WHITE_BORDER, fill=(255, 255, 255))
    return _recognize(final_crop, ocr_model_name=ocr_model_name)


__all__ = ["OCR_WHITE_BORDER", "_int_crop_box", "_recognize", "ocr_image_region"]
