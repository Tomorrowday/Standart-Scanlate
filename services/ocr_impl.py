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
from services.detector_ops.overlap_resolver import find_text_core_bbox

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


def _mask_foreign_neighbor_regions_in_page_coords(
    arr: np.ndarray,
    arr_box_px: Tuple[int, int, int, int],
    target_box_px: Tuple[int, int, int, int],
    img_size: Tuple[int, int],
    other_boxes: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Затирает белым цветом пиксели соседних баблов (классы 0 и 1), попавшие внутрь области arr (in-place).

    arr_box_px    — координаты самого массива arr на странице (sx1, sy1, sx2, sy2) в пикселях;
    target_box_px — координаты целевого бабла A на странице (x1, y1, x2, y2) в пикселях.
    """
    if not other_boxes:
        return

    sx1, sy1, sx2, sy2 = arr_box_px
    x1, y1, x2, y2 = target_box_px
    img_w, img_h = img_size

    acx, acy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    aw, ah = max(4.0, float(x2 - x1)), max(4.0, float(y2 - y1))

    # Находим собственное текстовое ядро целевого бабла A (в глобальных координатах страницы),
    # чтобы гарантированно защитить его от стирания
    ta_lx1 = max(0, x1 - sx1)
    ta_ly1 = max(0, y1 - sy1)
    ta_lx2 = min(arr.shape[1], x2 - sx1)
    ta_ly2 = min(arr.shape[0], y2 - sy1)
    gray_target = (
        cv2.cvtColor(arr[ta_ly1:ta_ly2, ta_lx1:ta_lx2], cv2.COLOR_RGB2GRAY)
        if (ta_lx2 > ta_lx1 and ta_ly2 > ta_ly1)
        else None
    )

    yy, xx = np.mgrid[sy1:sy2, sx1:sx2]

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

        # Пересечение соседа B с областью массива arr
        ix1, iy1 = max(sx1, ox1), max(sy1, oy1)
        ix2, iy2 = min(sx2, ox2), min(sy2, oy2)
        if ix2 <= ix1 + 2 or iy2 <= iy1 + 2:
            continue

        bcx, bcy = (ox1 + ox2) / 2.0, (oy1 + oy2) / 2.0
        if abs(acx - bcx) < 2 and abs(acy - bcy) < 2:
            continue

        bw, bh = max(4.0, float(ox2 - ox1)), max(4.0, float(oy2 - oy1))

        # Спорная зона в локальных координатах target_roi для поиска чистого ядра A
        ov_tx1 = max(0, ox1 - x1)
        ov_ty1 = max(0, oy1 - y1)
        ov_tx2 = min(int(aw), ox2 - x1)
        ov_ty2 = min(int(ah), oy2 - y1)
        exclude_rect = (
            (ov_tx1, ov_ty1, ov_tx2, ov_ty2)
            if (ov_tx2 > ov_tx1 and ov_ty2 > ov_ty1)
            else None
        )

        core_a = (
            find_text_core_bbox(gray_target, exclude_rect=exclude_rect)
            if gray_target is not None
            else None
        )

        # Опорная граница бабла A в сторону соседа B:
        # никогда не используем раздутый радиус чужого большого бабла B против маленького A!
        # Разделяющая плоскость проходит посередине между внутренними границами пересечения
        # (или сразу за текстовым ядром A, если ядро найдено).
        lx1, ly1 = ix1 - sx1, iy1 - sy1
        lx2, ly2 = ix2 - sx1, iy2 - sy1

        sub_xx = xx[ly1:ly2, lx1:lx2]
        sub_yy = yy[ly1:ly2, lx1:lx2]

        dx = bcx - acx
        dy = bcy - acy
        norm_dx = abs(dx) / ((aw + bw) / 2.0)
        norm_dy = abs(dy) / ((ah + bh) / 2.0)

        # Середина зоны пересечения двух рамок (нейтральная граница без перекоса в пользу большого бабла)
        mid_ov_x = (max(x1, ox1) + min(x2, ox2)) / 2.0
        mid_ov_y = (max(y1, oy1) + min(y2, oy2)) / 2.0

        if norm_dy >= norm_dx:
            # Баблы расположены преимущественно друг над другом: делим по горизонтали (Y)
            if dy > 0:
                # Сосед B ниже бабла A
                safe_y = (y1 + ta_ly1 - (y1 - sy1) + core_a[3] + 2) if core_a is not None else mid_ov_y
                cut_y = max(mid_ov_y, min(float(y2), float(safe_y)))
                foreign_mask = sub_yy > cut_y
            else:
                # Сосед B выше бабла A
                safe_y = (y1 + ta_ly1 - (y1 - sy1) + core_a[1] - 2) if core_a is not None else mid_ov_y
                cut_y = min(mid_ov_y, max(float(y1), float(safe_y)))
                foreign_mask = sub_yy < cut_y
        else:
            # Баблы расположены преимущественно слева/справа: делим по вертикали (X)
            if dx > 0:
                # Сосед B правее бабла A
                safe_x = (x1 + ta_lx1 - (x1 - sx1) + core_a[2] + 2) if core_a is not None else mid_ov_x
                cut_x = max(mid_ov_x, min(float(x2), float(safe_x)))
                foreign_mask = sub_xx > cut_x
            else:
                # Сосед B левее бабла A
                safe_x = (x1 + ta_lx1 - (x1 - sx1) + core_a[0] - 2) if core_a is not None else mid_ov_x
                cut_x = min(mid_ov_x, max(float(x1), float(safe_x)))
                foreign_mask = sub_xx < cut_x

        # Дополнительно защищаем собственное текстовое ядро бабла A от любого затирания
        if core_a is not None:
            core_gx1 = x1 + core_a[0] - 1
            core_gy1 = y1 + core_a[1] - 1
            core_gx2 = x1 + core_a[2] + 1
            core_gy2 = y1 + core_a[3] + 1
            inside_own_core = (
                (sub_xx >= core_gx1)
                & (sub_xx <= core_gx2)
                & (sub_yy >= core_gy1)
                & (sub_yy <= core_gy2)
            )
            foreign_mask = foreign_mask & (~inside_own_core)

        region = arr[ly1:ly2, lx1:lx2]
        region[foreign_mask] = [255, 255, 255]


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
    return _recognize(final_crop)
