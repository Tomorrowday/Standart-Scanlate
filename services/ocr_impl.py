# services/ocr_impl.py
# Потокобезопасное распознавание японского текста (MangaOCR) без лишнего сброса кэша VRAM на каждый бабл

import math
import re
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
import torch
from ml.models import ml

# Белое поле, которое добавляется вокруг уже вырезанного и очищенного кропа.
# Оно нужно MangaOCR для комфортного распознавания, но НЕ захватывает пиксели соседних баблов.
OCR_WHITE_BORDER = 12


def normalize_ocr_japanese_text(text: str) -> str:
    """Пост-процессинг пунктуации после распознавания."""
    if not text:
        return ""

    cleaned = text
    cleaned = re.sub(r'[:：]{2,}', '……', cleaned)
    cleaned = re.sub(r'(?<!\d)[:：](?!\d)', '…', cleaned)
    cleaned = re.sub(r'\.{2,}', '…', cleaned)
    cleaned = re.sub(r'[.…]{2,}', '…', cleaned)
    cleaned = re.sub(r'\s*…\s*', '…', cleaned)

    return cleaned.strip()


def _clean_ocr_crop_from_foreign_text(
    crop_pil: Image.Image,
    crop_box_px: Tuple[int, int, int, int],
    img_size: Tuple[int, int],
    class_id: int = 0,
    other_boxes: Optional[List[Dict[str, Any]]] = None,
) -> Image.Image:
    """
    Очищает кроп баббла (классы 0 и 1) перед MangaOCR:
    1) Маскирует белым цветом зоны пересечения с соседними бабблами, которые ближе к центру соседа.
    2) Стирает в белый цвет стенки баббла и разрезанные куски чужих иероглифов, прилипшие к краю рамки.

    crop_box_px — координаты кропа на исходной странице (x1, y1, x2, y2) в пикселях.
    other_boxes — соседние блоки страницы в нормализованных координатах (x, y, width, height, class_id).
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

    x1, y1, x2, y2 = crop_box_px
    img_w, img_h = img_size
    acx, acy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

    # 1. Если есть пересечение с соседними бабблами (например, диагональные сдвоенные бабблы),
    # отсекаем полуплоскость, принадлежащую соседу (диаграмма Вороного между центрами).
    if other_boxes:
        yy, xx = np.mgrid[y1:y2, x1:x2]
        for ob in other_boxes:
            try:
                if int(ob.get("class_id", 0)) not in (0, 1):
                    continue
                ox1 = int(float(ob["x"]) * img_w)
                oy1 = int(float(ob["y"]) * img_h)
                ox2 = int((float(ob["x"]) + float(ob["width"])) * img_w)
                oy2 = int((float(ob["y"]) + float(ob["height"])) * img_h)
            except (KeyError, TypeError, ValueError):
                continue

            ix1, iy1 = max(x1, ox1), max(y1, oy1)
            ix2, iy2 = min(x2, ox2), min(y2, oy2)
            if ix2 <= ix1 + 2 or iy2 <= iy1 + 2:
                continue

            bcx, bcy = (ox1 + ox2) / 2.0, (oy1 + oy2) / 2.0
            if abs(acx - bcx) < 2 and abs(acy - bcy) < 2:
                continue

            # Локальные координаты пересечения внутри кропа
            lx1, ly1 = ix1 - x1, iy1 - y1
            lx2, ly2 = ix2 - x1, iy2 - y1

            sub_xx = xx[ly1:ly2, lx1:lx2]
            sub_yy = yy[ly1:ly2, lx1:lx2]

            # Полуоси эллипсов: нормализация на размеры баббла не даёт маленькому бабблу
            # «перетянуть» на себя текст большого только из-за близости к его центру
            arx = max(8.0, (x2 - x1) / 2.0)
            ary = max(8.0, (y2 - y1) / 2.0)
            brx = max(8.0, (ox2 - ox1) / 2.0)
            bry = max(8.0, (oy2 - oy1) / 2.0)

            # Нормализованное квадратичное расстояние до центров эллипсов A и B
            # (позволяет корректно делить перекрытие даже между огромным и маленьким бабблом)
            norm_dist_a = ((sub_xx - acx) / arx) ** 2 + ((sub_yy - acy) / ary) ** 2
            norm_dist_b = ((sub_xx - bcx) / brx) ** 2 + ((sub_yy - bcy) / bry) ** 2

            # Закрашиваем белым только те пиксели в зоне пересечения, которые глубже внутри эллипса соседа
            foreign_mask = norm_dist_b < norm_dist_a
            region = arr[ly1:ly2, lx1:lx2]
            region[foreign_mask] = [255, 255, 255]

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

        # Компонента считается разрезанной границей кропа только если она вплотную упирается в срез
        touches_cut_edge = (cx == 0 or cy == 0 or (cx + cw) >= w or (cy + ch) >= h)
        if not touches_cut_edge:
            continue

        cent_x, cent_y = centroids[lbl]
        is_bubble_wall = (cw > w * 0.45 or ch > h * 0.45)
        # И «маленькая», и «у самого края»: через and, чтобы не стереть длинную черту ー / 一
        # у края узкого бабла (она может быть широкой, но не прилипшей к срезу)
        is_edge_fragment = (
            cent_x < w * 0.07 or cent_x > w * 0.93 or
            cent_y < h * 0.07 or cent_y > h * 0.93
        ) and (cw < w * 0.28 and ch < h * 0.28)

        if is_bubble_wall or is_edge_fragment:
            erase_mask[labels == lbl] = True

    if np.any(erase_mask):
        arr[erase_mask] = [255, 255, 255]

    return Image.fromarray(arr)


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


def _recognize(crop_img: Image.Image) -> str:
    """Отправляет подготовленный кроп в MangaOCR под блокировкой MLManager."""
    mocr_instance = ml.mocr
    with ml.lock, torch.inference_mode():
        raw_text = mocr_instance(crop_img).strip()
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
) -> str:
    """
    Вырезает область бабла и распознает через MangaOCR.
    Выполняется под блокировкой MLManager для безопасности при параллельных запросах.

    Кроп вырезается строго по рамке бабла:
      * классы 0 и 1 (речь / мысли) — без внешнего паддинга, чтобы не захватить чужой текст;
      * классы 2 и 3 (свободный текст / SFX) — максимум +2px.
    Белое поле для MangaOCR добавляется уже после вырезания и очистки кропа.
    other_boxes — соседние боксы страницы (нормализованные x, y, width, height, class_id).
    """
    img_w, img_h = image.size

    cx = (x + width / 2.0) * img_w
    cy = (y + height / 2.0) * img_h
    bw = max(2, int(width * img_w))
    bh = max(2, int(height * img_h))

    # Внешний паддинг больше не «съедает» соседние баблы
    outward_pad = 2 if class_id in (2, 3) else 0

    # 1. Прямой кроп
    if abs(rotation) < 0.5:
        x1, y1, x2, y2 = _int_crop_box(cx, cy, bw, bh, img_w, img_h, outward_pad)

        if x2 <= x1 or y2 <= y1:
            return ""

        crop_img = image.crop((x1, y1, x2, y2))
        crop_img = _clean_ocr_crop_from_foreign_text(
            crop_img, (x1, y1, x2, y2), (img_w, img_h), class_id, other_boxes
        )
        crop_img = ImageOps.expand(crop_img, border=OCR_WHITE_BORDER, fill=(255, 255, 255))
        return _recognize(crop_img)

    # 2. Повернутый кроп
    radius = math.ceil(math.sqrt(bw * bw + bh * bh) / 2.0) + outward_pad + 4
    sub_x1 = max(0, int(cx - radius))
    sub_y1 = max(0, int(cy - radius))
    sub_x2 = min(img_w, int(cx + radius))
    sub_y2 = min(img_h, int(cy + radius))

    if sub_x2 <= sub_x1 or sub_y2 <= sub_y1:
        return ""

    sub_crop = image.crop((sub_x1, sub_y1, sub_x2, sub_y2))
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
    # В повернутой системе координат маскирование по соседям страницы неприменимо,
    # поэтому ограничиваемся очисткой краевых обрезков.
    final_crop = _clean_ocr_crop_from_foreign_text(
        final_crop, (rx1, ry1, rx2, ry2), (rotated_sub.width, rotated_sub.height), class_id, None
    )
    final_crop = ImageOps.expand(final_crop, border=OCR_WHITE_BORDER, fill=(255, 255, 255))
    return _recognize(final_crop)
