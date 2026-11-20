# services/cleaner_ops/stroke_cores.py
# Поиск ядер символов текста, фильтрация лайнарта, заливка полостей и захват обводки
# (белого/чёрного ореола вокруг букв). Используется маской клина «Авто-Кисть».

from typing import List, Tuple

import cv2
import numpy as np


def extract_polarity_candidates(
    ext_gray: np.ndarray,
    polarity: str,
    kernel_sizes: List[int],
) -> np.ndarray:
    """
    Выделяет кандидатов в штрихи букв заданной полярности ('dark' или 'light')
    комбинацией морфологического контраста (BlackHat/TopHat) на нескольких масштабах
    и абсолютного порога яркости. Мультимасштабность нужна, чтобы одинаково уверенно
    находить и мелкий текст, и крупные SFX с толщиной штриха заметно больше 25px.
    """
    raw = np.zeros(ext_gray.shape, dtype=bool)

    for k in kernel_sizes:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        if polarity == "dark":
            contrast = cv2.morphologyEx(ext_gray, cv2.MORPH_BLACKHAT, kernel)
            raw |= (contrast >= 28) & (ext_gray < 210)
        else:
            contrast = cv2.morphologyEx(ext_gray, cv2.MORPH_TOPHAT, kernel)
            raw |= (contrast >= 28) & (ext_gray > 45)

    # Абсолютные пороги добирают «тело» жирных штрихов, которое не влезает в ядро морфологии
    if polarity == "dark":
        raw |= ext_gray < 145
    else:
        raw |= ext_gray > 215

    return raw.astype(np.uint8) * 255


def _paint_component(
    canvas: np.ndarray,
    labels: np.ndarray,
    label: int,
    x: int,
    y: int,
    w: int,
    h: int,
):
    """Закрашивает 255 только пиксели указанной компоненты внутри её bounding box."""
    sub_labels = labels[y:y + h, x:x + w]
    canvas[y:y + h, x:x + w][sub_labels == label] = 255


def _is_line_art_component(
    w: int,
    h: int,
    area: int,
    min_side: float,
) -> bool:
    """
    Отсекает тонкие протяжённые линии лайнарта (волосы, штриховка, контуры персонажей).
    Штрихи иероглифов компактны: их bounding box заполнен заметно плотнее,
    а длина редко превышает заметную долю рамки.
    """
    bbox_area = float(max(1, w * h))
    bbox_fill = area / bbox_area
    max_dim = max(w, h)
    aspect = max_dim / float(max(1, min(w, h)))

    # Длинная тонкая линия, у которой внутри bbox почти нет заполнения
    if bbox_fill < 0.14 and max_dim > 0.18 * min_side:
        return True
    # Очень вытянутая тонкая линия
    if aspect > 7.0 and bbox_fill < 0.20 and max_dim > 0.10 * min_side:
        return True
    return False


def filter_text_components(
    cand_mask: np.ndarray,
    pad_top: int,
    pad_left: int,
    roi_h: int,
    roi_w: int,
) -> Tuple[np.ndarray, float]:
    """
    Отфильтровывает из бинарной маски кандидатов:
      1) Линии лайнарта (волосы, одежда, рамки фреймов), которые уходят в технический
         внешний пояс за пределами рамки бабла, тянутся от края до края или слишком тонки.
      2) Мелкий регулярный шум скринтона, сохраняя при этом диакритику (゛, ゜) и пунктуацию.
      3) Сплошные «кляксы» арта (заливки, пятна волос) по толщине штриха.
    Возвращает (очищенную маску размера roi_h x roi_w, оценку качества полярности).
    """
    ext_h, ext_w = cand_mask.shape[:2]
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cand_mask, connectivity=8)

    if num_labels <= 1:
        return np.zeros((roi_h, roi_w), dtype=np.uint8), 0.0

    # Координаты внутренней целевой рамки бабла внутри расширенного патча
    box_x1, box_y1 = pad_left, pad_top
    box_x2, box_y2 = pad_left + roi_w, pad_top + roi_h
    box_area = float(max(1, roi_h * roi_w))
    min_side = float(min(roi_h, roi_w))

    # Карта толщины штрихов: тонкие линии лайнарта (1-2 px) имеют малое значение,
    # а штрихи шрифта — заметно большее.
    thickness_map = cv2.distanceTransform((cand_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
    min_stroke_thickness = min(2.5, max(1.2, min_side * 0.02))
    min_major_dim = max(4, int(min_side * 0.035))

    major_strokes_mask = np.zeros((ext_h, ext_w), dtype=np.uint8)
    small_dots_labels = []
    valid_components_count = 0
    total_valid_area = 0

    for lbl in range(1, num_labels):
        x = int(stats[lbl, cv2.CC_STAT_LEFT])
        y = int(stats[lbl, cv2.CC_STAT_TOP])
        w = int(stats[lbl, cv2.CC_STAT_WIDTH])
        h = int(stats[lbl, cv2.CC_STAT_HEIGHT])
        area = int(stats[lbl, cv2.CC_STAT_AREA])
        cx, cy = centroids[lbl]

        # 1. Центр тяжести компоненты обязан лежать внутри самой рамки бабла
        if not (box_x1 <= cx < box_x2 and box_y1 <= cy < box_y2):
            continue

        # 2. Отсекаем гигантские фоновые заливки (> 45% всей площади рамки)
        if area > box_area * 0.45:
            continue

        # 3. Проверяем, уходит ли компонента во внешний пояс за пределы рамки (лайнарт фона/персонажа)
        crosses_outer_left = x < max(1, box_x1 - 1)
        crosses_outer_right = (x + w) > min(ext_w - 1, box_x2 + 1)
        crosses_outer_top = y < max(1, box_y1 - 1)
        crosses_outer_bottom = (y + h) > min(ext_h - 1, box_y2 + 1)
        crosses_count = (
            int(crosses_outer_left)
            + int(crosses_outer_right)
            + int(crosses_outer_top)
            + int(crosses_outer_bottom)
        )

        # Если линия пронзает рамку насквозь (с двух сторон) или уходит наружу и слишком длинная — это арт
        if crosses_count >= 2:
            continue
        if crosses_count == 1 and (w > roi_w * 0.55 or h > roi_h * 0.55):
            continue

        # 4. Длинные тонкие линии вдоль самого края рамки (осколки рамки фрейма)
        near_edge = (
            (cx - box_x1) < roi_w * 0.06
            or (box_x2 - cx) < roi_w * 0.06
            or (cy - box_y1) < roi_h * 0.06
            or (box_y2 - cy) < roi_h * 0.06
        )
        if near_edge and (w > roi_w * 0.65 or h > roi_h * 0.65):
            continue

        # 5. Тонкие протяжённые линии лайнарта (волосы, штриховка, контуры)
        if _is_line_art_component(w, h, area, min_side):
            continue

        # 6. Разделяем уверенные штрихи букв и мелкие точки (потенциальный скринтон или дакутэн/точки)
        is_major = area >= 10 and max(w, h) >= min_major_dim
        if is_major:
            sub_lab = labels[y:y + h, x:x + w]
            sub_thickness = thickness_map[y:y + h, x:x + w]
            stroke_thickness = float(sub_thickness[sub_lab == lbl].max())
            # Слишком тонкая компонента — это не штрих шрифта, а линия рисунка/шум скринтона
            if stroke_thickness < min_stroke_thickness:
                continue
            # Сплошное массивное «пятно» арта (клякса волос, заливка одежды):
            # имеет большую толщину одновременно с крупными габаритами по обеим осям
            # и плотным заполнением bbox. Одиночные штрихи (ー, 一, ！) имеют малую
            # min(w, h), поэтому их отсекать нельзя.
            bbox_fill = area / float(max(1, w * h))
            if (
                stroke_thickness > max(10.0, min_side * 0.14)
                and min(w, h) > max(18.0, min_side * 0.26)
                and bbox_fill > 0.68
                and area > box_area * 0.025
            ):
                continue
            _paint_component(major_strokes_mask, labels, lbl, x, y, w, h)
            valid_components_count += 1
            total_valid_area += area
        elif area >= 3:
            small_dots_labels.append(lbl)

    if valid_components_count == 0:
        return np.zeros((roi_h, roi_w), dtype=np.uint8), 0.0

    # 7. Возвращаем мелкие точки ТОЛЬКО если они находятся рядом с крупными штрихами букв
    # (сохраняет дакутэн ゛, хандакутэн ゜, многоточия … и знаки ! ?, но отсекает точки скринтона на фоне)
    if small_dots_labels:
        proximity_radius = max(5, min(10, int(min_side * 0.05)))
        prox_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (proximity_radius * 2 + 1, proximity_radius * 2 + 1)
        )
        text_vicinity = cv2.dilate(major_strokes_mask, prox_kernel, iterations=1)
        for lbl in small_dots_labels:
            cx, cy = int(centroids[lbl][0]), int(centroids[lbl][1])
            if 0 <= cy < ext_h and 0 <= cx < ext_w and text_vicinity[cy, cx] > 0:
                x = int(stats[lbl, cv2.CC_STAT_LEFT])
                y = int(stats[lbl, cv2.CC_STAT_TOP])
                w = int(stats[lbl, cv2.CC_STAT_WIDTH])
                h = int(stats[lbl, cv2.CC_STAT_HEIGHT])
                _paint_component(major_strokes_mask, labels, lbl, x, y, w, h)

    cropped_core = major_strokes_mask[box_y1:box_y2, box_x1:box_x2]

    # Оценка «похожести на текст»: текст обычно занимает от 2% до 38% площади рамки
    # и состоит из нескольких компактных символов. Слишком большая заливка — это арт.
    fill_ratio = total_valid_area / box_area
    if fill_ratio < 0.005 or fill_ratio > 0.42:
        score = fill_ratio * 0.2
    else:
        score = min(valid_components_count, 25) * (1.0 - abs(fill_ratio - 0.14) * 1.5)

    return cropped_core, float(max(0.0, score))


def fill_inner_holes(binary: np.ndarray, max_hole_ratio: float = 0.30) -> np.ndarray:
    """
    Заливает замкнутые внутренние полости символов и их обводок (目, 前, 清, 春),
    чтобы внутри крупных кандзи не оставалось незамаскированных островков фона.
    Пропускает полости крупнее max_hole_ratio площади рамки (это уже фон, а не буква).
    """
    filled = binary.copy()
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return filled

    max_hole_area = max(16.0, float(binary.shape[0] * binary.shape[1]) * max_hole_ratio)
    for idx, cnt in enumerate(contours):
        if hierarchy[0][idx][3] == -1:
            continue  # внешний контур, а не полость
        if cv2.contourArea(cnt) <= max_hole_area:
            cv2.drawContours(filled, [cnt], -1, 255, thickness=-1)
    return filled


def grow_halo_around_strokes(
    roi_gray: np.ndarray,
    core_mask: np.ndarray,
    polarity: str,
    max_halo_px: int,
) -> Tuple[np.ndarray, int]:
    """
    Геодезически расширяет маску букв на их контрастную обводку (ореол / stroke)
    и оценивает её реальную толщину. Возвращает (маска_ядра_с_обводкой, толщина_обводки_px).
    """
    if not np.any(core_mask):
        return core_mask.copy(), 0

    if polarity == "dark":
        # Белая/светлая обводка вокруг тёмных букв (включая сглаженные края на скринтоне)
        halo_candidates = (roi_gray >= 214).astype(np.uint8) * 255
    else:
        # Чёрная/тёмная обводка вокруг белых букв
        halo_candidates = (roi_gray <= 58).astype(np.uint8) * 255

    step_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grown = core_mask.copy()

    saturated = False
    for step in range(max_halo_px):
        dilated = cv2.dilate(grown, step_kernel, iterations=1)
        next_grown = cv2.bitwise_or(grown, cv2.bitwise_and(dilated, halo_candidates))
        if np.array_equal(next_grown, grown):
            break
        grown = next_grown
        saturated = step == max_halo_px - 1

    halo_pixels = (grown > 0) & (core_mask == 0)
    if not np.any(halo_pixels):
        return grown, 0

    dist_from_core = cv2.distanceTransform((core_mask == 0).astype(np.uint8), cv2.DIST_L2, 5)
    thickness = int(round(float(np.percentile(dist_from_core[halo_pixels], 90))))
    thickness = int(np.clip(thickness, 0, max_halo_px))

    # Если рост упёрся в предел max_halo_px, значит ореол слился с однотонным фоном:
    # ограничиваем толщину и возвращаем аккуратную дилатацию вместо залитого фона.
    if saturated:
        thickness = min(thickness, 3)
        if thickness > 0:
            k = 2 * thickness + 1
            kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            grown = cv2.dilate(core_mask, kern, iterations=1)
        else:
            grown = core_mask.copy()

    return grown, thickness
