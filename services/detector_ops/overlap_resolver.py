# services/detector_ops/overlap_resolver.py
# Алгоритм разделения перекрывающихся (сдвоенных) бабблов по белой просеке между их текстовыми ядрами

from typing import List, Tuple, Optional
import cv2
import numpy as np


def find_text_core_bbox(
    gray_roi: np.ndarray,
    exclude_rect: Optional[Tuple[int, int, int, int]] = None
) -> Optional[Tuple[int, int, int, int]]:
    """
    Находит узкий ограничивающий прямоугольник (x1, y1, x2, y2) собственного текстового ядра
    внутри ROI баббла, отсекая внешние рамки баббла и компоненты, лежащие целиком внутри
    спорной зоны exclude_rect.

    exclude_rect — зона пересечения с соседним бабблом в ЛОКАЛЬНЫХ координатах gray_roi.
    Компоненты, чей центр тяжести лежит внутри этой зоны, считаются чужим текстом
    и не растягивают ядро на соседа.

    Возвращает локальные координаты относительно gray_roi или None, если текст не найден.
    """
    if gray_roi is None or gray_roi.size == 0:
        return None

    h, w = gray_roi.shape[:2]
    if h < 8 or w < 8:
        return None

    # Бинаризация темных пикселей (текст + контур)
    dark = (gray_roi < 190).astype(np.uint8) * 255
    num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(dark, connectivity=8)

    edge_margin = 2
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    found = False

    for lbl in range(1, num_labels):
        cx = int(stats[lbl, cv2.CC_STAT_LEFT])
        cy = int(stats[lbl, cv2.CC_STAT_TOP])
        cw = int(stats[lbl, cv2.CC_STAT_WIDTH])
        ch = int(stats[lbl, cv2.CC_STAT_HEIGHT])
        area = int(stats[lbl, cv2.CC_STAT_AREA])

        if area < 3:
            continue

        touches_edge = (
            cx <= edge_margin
            or cy <= edge_margin
            or (cx + cw) >= w - edge_margin
            or (cy + ch) >= h - edge_margin
        )
        # Отбрасываем длинные линии контура самого баббла, касающиеся краев
        if touches_edge and (cw > w * 0.45 or ch > h * 0.45):
            continue

        # Отбрасываем буквы соседа, попавшие в зону пересечения:
        # их центр тяжести лежит глубоко внутри спорной зоны
        if exclude_rect is not None:
            ex1, ey1, ex2, ey2 = exclude_rect
            cent_x, cent_y = centroids[lbl]
            if ex1 <= cent_x <= ex2 and ey1 <= cent_y <= ey2:
                continue

        min_x = min(min_x, cx)
        min_y = min(min_y, cy)
        max_x = max(max_x, cx + cw)
        max_y = max(max_y, cy + ch)
        found = True

    if not found or max_x <= min_x or max_y <= min_y:
        return None

    return min_x, min_y, max_x, max_y


def _find_whitespace_split(profile: np.ndarray) -> int:
    """
    Находит индекс наилучшего разреза в 1D-профиле плотности темных пикселей.
    Предпочитает самую широкую белую полосу (где нет букв), а при наличии перешейка — точку минимума.
    """
    n = len(profile)
    if n <= 2:
        return n // 2

    is_empty = profile < 0.025
    if np.any(is_empty):
        runs = []
        i = 0
        while i < n:
            if not is_empty[i]:
                i += 1
                continue
            j = i
            while j < n and is_empty[j]:
                j += 1
            runs.append((i, j))
            i = j

        mid = n / 2.0
        best_run = max(
            runs,
            key=lambda r: (r[1] - r[0]) - abs(((r[0] + r[1]) / 2.0) - mid) * 0.15
        )
        best_idx = (best_run[0] + best_run[1]) // 2
    else:
        weights = 1.0 + 0.25 * np.abs(np.linspace(-1.0, 1.0, n))
        best_idx = int(np.argmin(profile * weights))

    return max(1, min(n - 1, best_idx))


def _find_split_between_cores(
    profile: np.ndarray,
    offset: int,
    gap_start: int,
    gap_end: int,
    region_start: int,
    region_end: int,
) -> int:
    """
    Ищет белую просеку строго в зазоре между краями двух текстовых ядер.

    profile     — 1D-профиль плотности тёмных пикселей вдоль оси разреза,
                  где индекс 0 соответствует абсолютной координате offset;
    gap_start / gap_end — абсолютные координаты краёв зазора между ядрами
                  (например, a_core_y2 и b_core_y1);
    region_start / region_end — абсолютные границы зоны пересечения.

    Разрез гарантированно не заходит внутрь ядер: он зажат в диапазон
    max(region_start + 1, gap_start + 2) .. min(region_end - 1, gap_end - 2).
    """
    n = int(profile.shape[0]) if profile is not None else 0

    # Окно между ядрами, пересечённое с профилем
    gs = max(0, gap_start - offset)
    ge = min(n, gap_end - offset) if n > 0 else 0

    if ge - gs >= 2:
        split = offset + gs + _find_whitespace_split(profile[gs:ge])
    else:
        # Зазор целиком вне профиля — делим посередине зазора
        split = (gap_start + gap_end) // 2

    lo = max(region_start + 1, gap_start + 2)
    hi = min(region_end - 1, gap_end - 2)

    if lo > hi:
        # Зазор слишком узкий для отступов — режем ровно посередине между ядрами
        middle = (gap_start + gap_end) // 2
        lo = hi = max(region_start + 1, min(region_end - 1, middle))

    return int(max(lo, min(hi, split)))


def resolve_overlapping_bubbles(
    gray_img: np.ndarray,
    boxes: List[Tuple[int, int, int, int, int]]
) -> List[Tuple[int, int, int, int, int]]:
    """
    Принимает список (x1, y1, x2, y2, cls_id) в пикселях.
    Для перекрывающихся бабблов (cls_id 0 и 1) находит границу между их текстами
    и разводит рамки так, чтобы они не захватывали чужой текст.
    """
    if not boxes:
        return []

    res = [list(b) for b in boxes]
    n = len(res)

    for i in range(n):
        if res[i][4] not in (0, 1):
            continue

        for j in range(i + 1, n):
            if res[j][4] not in (0, 1):
                continue

            ax1, ay1, ax2, ay2, _ = res[i]
            bx1, by1, bx2, by2, _ = res[j]

            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)

            iw = ix2 - ix1
            ih = iy2 - iy1

            # Если пересечение незначительное (менее 4px) — пропускаем
            if iw <= 4 or ih <= 4:
                continue

            aw, ah = max(1, ax2 - ax1), max(1, ay2 - ay1)
            bw, bh = max(1, bx2 - bx1), max(1, by2 - by1)

            # Зона пересечения в локальных координатах каждого ROI:
            # буквы соседа, попавшие сюда, не должны растягивать наше ядро
            local_ov_a = (ix1 - ax1, iy1 - ay1, ix2 - ax1, iy2 - ay1)
            local_ov_b = (ix1 - bx1, iy1 - by1, ix2 - bx1, iy2 - by1)
            roi_a = gray_img[ay1:ay2, ax1:ax2]
            roi_b = gray_img[by1:by2, bx1:bx2]

            # Определяем центры текстовых ядер (если удалось найти) или геометрические центры
            core_a = (
                find_text_core_bbox(roi_a, exclude_rect=local_ov_a)
                or find_text_core_bbox(roi_a)
            )
            core_b = (
                find_text_core_bbox(roi_b, exclude_rect=local_ov_b)
                or find_text_core_bbox(roi_b)
            )

            if core_a is not None:
                acx = ax1 + (core_a[0] + core_a[2]) / 2.0
                acy = ay1 + (core_a[1] + core_a[3]) / 2.0
            else:
                acx, acy = (ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0

            if core_b is not None:
                bcx = bx1 + (core_b[0] + core_b[2]) / 2.0
                bcy = by1 + (core_b[1] + core_b[3]) / 2.0
            else:
                bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0

            norm_dx = abs(acx - bcx) / ((aw + bw) / 2.0)
            norm_dy = abs(acy - bcy) / ((ah + bh) / 2.0)

            overlap_roi = gray_img[iy1:iy2, ix1:ix2]
            if overlap_roi.size == 0:
                continue

            # Чтобы боковые черные рамки баббла не мешали найти белую просеку между текстами,
            # отступаем внутрь области пересечения от краев
            dark_mask = (overlap_roi < 190).astype(np.float32)

            # Выбираем ось разреза: вдоль той оси, по которой центры разнесены сильнее
            if norm_dy >= norm_dx:
                # Бабблы расположены ДРУГ НАД ДРУГОМ -> режем по горизонтали (ось Y)
                margin_x = min(6, iw // 4)
                inner_x1, inner_x2 = margin_x, max(margin_x + 1, iw - margin_x)
                row_profile = np.mean(dark_mask[:, inner_x1:inner_x2], axis=1)

                split_y = iy1 + _find_whitespace_split(row_profile)

                # Не даем разрезу залезть внутрь известного текстового ядра (если ядра не пересекаются по Y)
                if core_a is not None and core_b is not None:
                    a_core_y1, a_core_y2 = ay1 + core_a[1], ay1 + core_a[3]
                    b_core_y1, b_core_y2 = by1 + core_b[1], by1 + core_b[3]
                    if acy < bcy and a_core_y2 < b_core_y1:
                        # Ищем именно белую просеку в зазоре между ядрами, а не слепую середину
                        split_y = _find_split_between_cores(
                            row_profile, iy1, a_core_y2, b_core_y1, iy1, iy2
                        )
                    elif bcy < acy and b_core_y2 < a_core_y1:
                        split_y = _find_split_between_cores(
                            row_profile, iy1, b_core_y2, a_core_y1, iy1, iy2
                        )

                if acy < bcy:
                    if split_y - ay1 >= 16 and by2 - split_y >= 16:
                        res[i][3] = max(ay1 + 16, split_y - 1)
                        res[j][1] = min(by2 - 16, split_y + 1)
                else:
                    if split_y - by1 >= 16 and ay2 - split_y >= 16:
                        res[j][3] = max(by1 + 16, split_y - 1)
                        res[i][1] = min(ay2 - 16, split_y + 1)
            else:
                # Бабблы расположены СЛЕВА И СПРАВА -> режем по вертикали (ось X)
                margin_y = min(6, ih // 4)
                inner_y1, inner_y2 = margin_y, max(margin_y + 1, ih - margin_y)
                col_profile = np.mean(dark_mask[inner_y1:inner_y2, :], axis=0)

                split_x = ix1 + _find_whitespace_split(col_profile)

                if core_a is not None and core_b is not None:
                    a_core_x1, a_core_x2 = ax1 + core_a[0], ax1 + core_a[2]
                    b_core_x1, b_core_x2 = bx1 + core_b[0], bx1 + core_b[2]
                    if acx < bcx and a_core_x2 < b_core_x1:
                        split_x = _find_split_between_cores(
                            col_profile, ix1, a_core_x2, b_core_x1, ix1, ix2
                        )
                    elif bcx < acx and b_core_x2 < a_core_x1:
                        split_x = _find_split_between_cores(
                            col_profile, ix1, b_core_x2, a_core_x1, ix1, ix2
                        )

                if acx < bcx:
                    if split_x - ax1 >= 16 and bx2 - split_x >= 16:
                        res[i][2] = max(ax1 + 16, split_x - 1)
                        res[j][0] = min(bx2 - 16, split_x + 1)
                else:
                    if split_x - bx1 >= 16 and ax2 - split_x >= 16:
                        res[j][2] = max(bx1 + 16, split_x - 1)
                        res[i][0] = min(ax2 - 16, split_x + 1)

    return [(b[0], b[1], b[2], b[3], b[4]) for b in res]
