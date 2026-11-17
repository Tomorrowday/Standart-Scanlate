# services/ocr_ops/neighbor_masking.py
# Затирание пикселей соседних баблов внутри кропа перед распознаванием (без перекоса по размеру)

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from services.detector_ops.overlap_resolver import find_text_core_bbox


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
                # Сосед B ниже бабла A: режем сразу за собственным ядром A, не зажимая к mid_ov_y
                if core_a is not None:
                    safe_y = y1 + core_a[3] + 2
                    cut_y = max(float(iy1), min(float(iy2), float(safe_y)))
                else:
                    cut_y = mid_ov_y
                foreign_mask = sub_yy > cut_y
            else:
                # Сосед B выше бабла A
                if core_a is not None:
                    safe_y = y1 + core_a[1] - 2
                    cut_y = max(float(iy1), min(float(iy2), float(safe_y)))
                else:
                    cut_y = mid_ov_y
                foreign_mask = sub_yy < cut_y
        else:
            # Баблы расположены преимущественно слева/справа: делим по вертикали (X)
            if dx > 0:
                # Сосед B правее бабла A
                if core_a is not None:
                    safe_x = x1 + core_a[2] + 2
                    cut_x = max(float(ix1), min(float(ix2), float(safe_x)))
                else:
                    cut_x = mid_ov_x
                foreign_mask = sub_xx > cut_x
            else:
                # Сосед B левее бабла A
                if core_a is not None:
                    safe_x = x1 + core_a[0] - 2
                    cut_x = max(float(ix1), min(float(ix2), float(safe_x)))
                else:
                    cut_x = mid_ov_x
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


__all__ = ["_mask_foreign_neighbor_regions_in_page_coords"]
