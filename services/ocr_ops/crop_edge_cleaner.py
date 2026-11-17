# services/ocr_ops/crop_edge_cleaner.py
# Очистка краёв кропа бабла от стенок пузыря и обрезанных чужих иероглифов

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from services.ocr_ops.neighbor_masking import _mask_foreign_neighbor_regions_in_page_coords


def _clean_ocr_crop_from_foreign_text(
    crop_pil: Image.Image,
    crop_box_px: Tuple[int, int, int, int],
    img_size: Tuple[int, int],
    class_id: int = 0,
    other_boxes: Optional[List[Dict[str, Any]]] = None,
) -> Image.Image:
    """
    Очищает кроп баббла (классы 0 и 1) перед MangaOCR:
    1) Маскирует белым цветом зоны пересечения с соседними бабблами без перекоса из-за разницы размеров.
    2) Стирает в белый цвет стенки баббла и разрезанные куски чужих иероглифов, прилипшие к краю рамки.
    """
    if class_id not in (0, 1):
        return crop_pil

    arr = np.array(crop_pil.convert("RGB"))
    h, w = arr.shape[:2]
    if h < 10 or w < 10:
        return crop_pil

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # Применяем очистку только для светлых бабблов с темным текстом
    if float(np.mean(gray > 195)) < 0.50:
        return crop_pil

    # 1. Маскируем области пересечения с соседними баблами
    if other_boxes:
        _mask_foreign_neighbor_regions_in_page_coords(
            arr=arr,
            arr_box_px=crop_box_px,
            target_box_px=crop_box_px,
            img_size=img_size,
            other_boxes=other_boxes,
        )

    # 2. Удаляем контуры рамки баббла и обрезки чужих букв, прилипшие вплотную к краям кропа
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    dark = (gray < 195).astype(np.uint8) * 255
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dark, connectivity=8)

    erase_mask = np.zeros((h, w), dtype=bool)
    for lbl in range(1, num_labels):
        cx = int(stats[lbl, cv2.CC_STAT_LEFT])
        cy = int(stats[lbl, cv2.CC_STAT_TOP])
        cw = int(stats[lbl, cv2.CC_STAT_WIDTH])
        ch = int(stats[lbl, cv2.CC_STAT_HEIGHT])

        touches_cut_edge = (cx == 0 or cy == 0 or (cx + cw) >= w or (cy + ch) >= h)
        if not touches_cut_edge:
            continue

        cent_x, cent_y = centroids[lbl]
        is_bubble_wall = (cw > w * 0.45 or ch > h * 0.45)
        is_edge_fragment = (
            cent_x < w * 0.07 or cent_x > w * 0.93 or
            cent_y < h * 0.07 or cent_y > h * 0.93
        ) and (cw < w * 0.28 and ch < h * 0.28)

        if is_bubble_wall or is_edge_fragment:
            erase_mask[labels == lbl] = True

    if np.any(erase_mask):
        arr[erase_mask] = [255, 255, 255]

    return Image.fromarray(arr)


__all__ = ["_clean_ocr_crop_from_foreign_text"]
