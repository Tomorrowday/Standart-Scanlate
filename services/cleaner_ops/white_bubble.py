# services/cleaner_ops/white_bubble.py
# Морфологическая очистка белых речевых баблов (с защитой лучистых/пунктирных рамок)

import math
from typing import Dict, List, Set, Tuple
import cv2
import numpy as np


def is_mostly_white_bubble(roi: np.ndarray, gray: np.ndarray) -> bool:
    if gray.size == 0:
        return False
    if np.mean(gray >= 238) < 0.70:
        return False
    if np.mean((gray >= 70) & (gray <= 215)) > 0.09:
        return False
    light_pixels = gray[gray >= 200]
    if light_pixels.size > 0 and np.std(light_pixels) > 12.0:
        return False
    return float(np.mean(gray)) >= 215.0


def _create_shape_mask(h: int, w: int, shape: str = "rect") -> np.ndarray:
    mask = np.zeros((h, w), dtype=np.uint8)
    if shape == "ellipse":
        cv2.ellipse(mask, (w // 2, h // 2), (w // 2, h // 2), 0, 0, 360, 255, -1)
    else:
        mask.fill(255)
    return mask


def _extract_center_white_component(binary_white: np.ndarray, h: int, w: int) -> np.ndarray:
    """Находит связную белую компоненту, покрывающую центральную зону бабла."""
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_white, connectivity=4)
    cy1, cy2 = int(h * 0.22), max(int(h * 0.22) + 1, int(h * 0.78))
    cx1, cx2 = int(w * 0.22), max(int(w * 0.22) + 1, int(w * 0.78))
    center_labels = np.unique(labels[cy1:cy2, cx1:cx2])

    interior = np.zeros((h, w), dtype=np.uint8)
    min_area = (h * w) * 0.04

    for lbl in center_labels:
        if lbl != 0 and stats[lbl, cv2.CC_STAT_AREA] >= min_area:
            interior[labels == lbl] = 255

    if np.sum(interior) == 0 and num_labels > 1:
        best_lbl = max(
            (lbl for lbl in center_labels if lbl != 0),
            key=lambda l: stats[l, cv2.CC_STAT_AREA],
            default=0,
        )
        if best_lbl > 0:
            interior[labels == best_lbl] = 255

    return interior


def _count_border_contact(mask: np.ndarray) -> int:
    """Считает количество пикселей маски, касающихся четырёх сторон ROI."""
    if mask.size == 0:
        return 0
    return int(
        np.sum(mask[0, :] > 0)
        + np.sum(mask[-1, :] > 0)
        + np.sum(mask[:, 0] > 0)
        + np.sum(mask[:, -1] > 0)
    )


def _stroke_orientation_deg(cnt: np.ndarray) -> float:
    """
    Ориентация главной оси штриха (PCA) в градусах [0..180).

    `cv2.minAreaRect` на коротких толстых штрихах часто «перекидывает» угол
    к ближайшей оси и даёт ложную разницу наклона ~30–40°. SVD по точкам
    контура устойчивее, поэтому соседние лучи распознаются корректно.
    """
    pts = cnt.reshape(-1, 2).astype(np.float64)
    if pts.shape[0] < 2:
        return 0.0
    centered = pts - pts.mean(axis=0)
    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return 0.0
    vx, vy = vh[0]
    return math.degrees(math.atan2(vy, vx)) % 180.0


def _build_white_core(gray: np.ndarray) -> Tuple[np.ndarray, int, int]:
    """
    Строит базовое белое ядро бабла и метрики контакта с краями ROI.

    Возвращает `(interior_white, border_pixels, perimeter)`.
    """
    h, w = gray.shape[:2]
    _, white_canvas = cv2.threshold(gray, 215, 255, cv2.THRESH_BINARY)
    kernel_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded_white = cv2.erode(white_canvas, kernel_3, iterations=1)
    interior_white = _extract_center_white_component(eroded_white, h, w)
    border_pixels = _count_border_contact(interior_white)
    perimeter = 2 * (h + w)
    return interior_white, border_pixels, perimeter


def _ring_octant_count(
    indices: Set[int],
    centers: Dict[int, Tuple[float, float]],
    h_roi: int,
    w_roi: int,
) -> int:
    """Считает число заполненных 45-градусных секторов (октантов) вокруг центра ROI."""
    octants: Set[int] = set()
    center_x, center_y = w_roi * 0.5, h_roi * 0.5
    for idx in indices:
        mx, my = centers.get(idx, (center_x, center_y))
        angle = math.degrees(math.atan2(my - center_y, mx - center_x)) % 360.0
        octants.add(int(angle // 45.0) % 8)
    return len(octants)


def _build_bubble_interior_mask(
    gray: np.ndarray,
    interior_white: np.ndarray,
    border_pixels: int,
    perimeter: int,
    barrier_mask: np.ndarray,
) -> Tuple[np.ndarray, bool]:
    """
    Строит внутреннюю маску бабла.

    Если белое ядро «протекает» к краям ROI и найдена маска барьера рамки,
    прогрессивно смыкает только элементы рамки (текст не эродируется и не
    сливается со стенками). Возвращает `(interior_mask, sealed_by_bridging)`.
    """
    h, w = gray.shape[:2]
    kernel_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    if border_pixels > perimeter * 0.06 and np.any(barrier_mask):
        # Перебираем ядра по возрастанию: сначала аккуратное смыкание,
        # затем более широкое — только если оно реально запечатало утечку.
        max_gap_k = max(7, min(15, int(min(h, w) * 0.05) | 1))
        gap_sizes = sorted(
            {gap_k for gap_k in (5, 9, 13, 15) if gap_k <= max_gap_k} | {max_gap_k}
        )

        for gap_k in gap_sizes:
            bridging_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap_k, gap_k))
            sealed_barrier = cv2.dilate(barrier_mask, bridging_kernel, iterations=1)
            # Мостим зазоры рамки, но не трогаем тёмный текст внутри ядра
            bridged_white = cv2.bitwise_not(sealed_barrier)
            sealed_core = _extract_center_white_component(bridged_white, h, w)

            if np.sum(sealed_core > 0) < (h * w) * 0.06:
                continue

            # Проверяем реальный факт запечатывания: ядро больше не должно
            # массово касаться краёв ROI.
            sealed_border = _count_border_contact(sealed_core)
            if not (
                sealed_border <= perimeter * 0.05
                or (sealed_border <= border_pixels * 0.45 and sealed_border <= perimeter * 0.22)
            ):
                continue

            # Успех: возвращаем ядро наружу, гарантируем отсутствие случайных
            # дыр и вычитаем защитный буфер рамки.
            restore_k = max(3, gap_k - 2) | 1
            restore_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (restore_k, restore_k))
            restored_white = cv2.dilate(sealed_core, restore_kernel, iterations=1)
            contours, _ = cv2.findContours(restored_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            interior_mask = np.zeros_like(gray)
            if contours:
                cv2.fillPoly(interior_mask, contours, 255)
            border_buffer = cv2.dilate(barrier_mask, kernel_3, iterations=1)
            interior_mask[border_buffer == 255] = 0
            # Намеренно НЕ вырезаем `gray < 180`: символы у самой стенки бабла
            # не должны продырявливать залив `interior_mask`.
            return interior_mask, True

    # Стандартная ветка: обычный белый бабл без лучистой/пунктирной рамки
    # либо обрезанный/тесный бокс, который запечатать не удалось.
    if np.sum(interior_white) == 0:
        interior_mask = np.full_like(gray, 255)
    else:
        interior_white = cv2.dilate(interior_white, kernel_3, iterations=1)
        interior_white[gray < 180] = 0
        contours, _ = cv2.findContours(interior_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        interior_mask = np.zeros_like(gray)
        if contours:
            cv2.fillPoly(interior_mask, contours, 255)
        interior_mask = cv2.erode(interior_mask, kernel_3, iterations=1)

    return interior_mask, False


def _detect_border_comb_ticks(
    contours: List[np.ndarray],
    h_roi: int,
    w_roi: int,
) -> Set[int]:
    """
    Находит индексы контуров, образующих «гребёнку» радиальных лучей по периметру бабла.

    Одиночные штрихи букв (!, は, い, 不) внутри белого поля сюда НЕ попадают, потому что:
      1) они лежат глубоко в центре или не прижаты к периферии;
      2) у них нет соседних параллельных зубцов гребёнки вдоль границы бабла;
      3) кандидаты обязаны образовывать замкнутое кольцо вокруг центра ROI.
    """
    candidates = []
    min_dim = float(min(h_roi, w_roi))
    max_short_side = max(8.0, min_dim * 0.04)

    for idx, cnt in enumerate(contours):
        if len(cnt) < 4:
            continue

        cx, cy, cw, ch = cv2.boundingRect(cnt)
        # Слишком крупные контуры обрабатываются отдельно
        if cw > w_roi * 0.35 or ch > h_roi * 0.35:
            continue

        (mcx, mcy), (mw, mh), _ = cv2.minAreaRect(cnt)
        long_side = max(mw, mh)
        short_side = max(1.0, min(mw, mh))
        aspect = long_side / short_side
        # нужен для коротких радиальных лучей у края ROI: их `minAreaRect`
        # с учётом толщины обводки часто даёт aspect ~1.5–2.2. Ложные
        # срабатывания на тексте отсекает глобальная проверка кольца ниже.
        if aspect < 1.5 or long_side < 4.0:
            continue
        if short_side > max_short_side:
            continue

        # Расстояние от центра штриха до ближайшего края ROI
        dist_to_roi_edge = min(mcx, w_roi - mcx, mcy, h_roi - mcy)
        near_roi_edge = dist_to_roi_edge <= max(18.0, min_dim * 0.14)

        # Нормализованный радиус от центра бабла (0 в центре, ~1 у краёв)
        nx = (mcx - w_roi * 0.5) / max(1.0, w_roi * 0.5)
        ny = (mcy - h_roi * 0.5) / max(1.0, h_roi * 0.5)
        radial_dist = math.hypot(nx, ny)

        # Глубокий центр — это всегда текст/знак, а не луч.
        if radial_dist < 0.45:
            continue
        if radial_dist < 0.58 and not near_roi_edge:
            continue

        # Ориентация главной оси штриха в градусах [0..180)
        theta_deg = _stroke_orientation_deg(cnt)
        theta_rad = math.radians(theta_deg)
        ux, uy = math.cos(theta_rad), math.sin(theta_rad)

        # Проверяем радиальность (направление примерно к центру бабла)
        vx = mcx - w_roi * 0.5
        vy = mcy - h_roi * 0.5
        v_norm = math.hypot(vx, vy)
        if v_norm < 1e-3:
            continue
        cos_sim = abs(ux * vx + uy * vy) / v_norm
        if cos_sim < 0.60:
            continue

        candidates.append((idx, mcx, mcy, long_side, theta_deg))

    # Оставляем только те штрихи, которые входят в «гребёнку» (минимум 2 соседа рядом
    # с близким углом наклона и сопоставимым размером)
    tick_indices: Set[int] = set()
    max_neighbor_dist = max(24.0, min_dim * 0.12)

    for i, (idx_a, x_a, y_a, len_a, ang_a) in enumerate(candidates):
        parallel_neighbors = 0
        for j, (idx_b, x_b, y_b, len_b, ang_b) in enumerate(candidates):
            if i == j:
                continue
            dist = math.hypot(x_a - x_b, y_a - y_b)
            if dist > max_neighbor_dist:
                continue
            ang_diff = abs(ang_a - ang_b)
            ang_diff = min(ang_diff, 180.0 - ang_diff)
            if ang_diff <= 28.0:
                parallel_neighbors += 1

        if parallel_neighbors >= 2:
            tick_indices.add(idx_a)

    if not tick_indices:
        return set()

    # Глобальная проверка кольца: лучи должны быть распределены по периметру,
    # а не лежать локальной группой у края ROI (например, штрихи текста «三»).
    centers: Dict[int, Tuple[float, float]] = {idx: (x, y) for idx, x, y, _, _ in candidates}
    octants = _ring_octant_count(tick_indices, centers, h_roi, w_roi)
    if len(tick_indices) >= 8 and octants >= 3:
        return tick_indices
    if len(tick_indices) >= 12 and octants >= 2:
        return tick_indices
    return set()


def _detect_perimeter_dashes(
    contours: List[np.ndarray],
    h_roi: int,
    w_roi: int,
) -> Set[int]:
    """
    Находит индексы тонких штрихов пунктирной (тангенциальной) рамки бабла.

    Штрихи ориентированы ПОПЕРЁК радиуса (вдоль контура овала), лежат
    на периферии ROI и образуют кольцо минимум по трём октантам.
    """
    candidates = []
    min_dim = float(min(h_roi, w_roi))
    max_short_side = max(8.0, min_dim * 0.04)

    for idx, cnt in enumerate(contours):
        if len(cnt) < 4:
            continue

        cx, cy, cw, ch = cv2.boundingRect(cnt)
        if cw > w_roi * 0.35 or ch > h_roi * 0.35:
            continue

        (mcx, mcy), (mw, mh), angle = cv2.minAreaRect(cnt)
        long_side = max(mw, mh)
        short_side = max(1.0, min(mw, mh))
        aspect = long_side / short_side

        # Тонкий вытянутый штрих
        if aspect < 1.8 or long_side < 4.0:
            continue
        if short_side > max_short_side:
            continue

        dist_to_roi_edge = min(mcx, w_roi - mcx, mcy, h_roi - mcy)
        near_roi_edge = dist_to_roi_edge <= max(18.0, min_dim * 0.14)

        nx = (mcx - w_roi * 0.5) / max(1.0, w_roi * 0.5)
        ny = (mcy - h_roi * 0.5) / max(1.0, h_roi * 0.5)
        radial_dist = math.hypot(nx, ny)

        # Периферийная зона, но не вплотную к центру
        if radial_dist < 0.55:
            continue
        if radial_dist < 0.68 and not near_roi_edge:
            continue

        theta_deg = (angle if mw >= mh else angle + 90.0) % 180.0
        theta_rad = math.radians(theta_deg)
        ux, uy = math.cos(theta_rad), math.sin(theta_rad)

        vx = mcx - w_roi * 0.5
        vy = mcy - h_roi * 0.5
        v_norm = math.hypot(vx, vy)
        if v_norm < 1e-3:
            continue

        # Тангенциальность: ось штриха почти перпендикулярна радиусу.
        cos_sim = abs(ux * vx + uy * vy) / v_norm
        if cos_sim > 0.48:
            continue

        candidates.append((idx, mcx, mcy, long_side, theta_deg))

    dash_indices: Set[int] = set()
    neighbor_dist = max(28.0, min_dim * 0.16)

    for i, (idx_a, x_a, y_a, len_a, ang_a) in enumerate(candidates):
        has_neighbor = False
        for j, (idx_b, x_b, y_b, len_b, ang_b) in enumerate(candidates):
            if i == j:
                continue
            dist = math.hypot(x_a - x_b, y_a - y_b)
            if dist > neighbor_dist:
                continue
            ang_diff = abs(ang_a - ang_b)
            ang_diff = min(ang_diff, 180.0 - ang_diff)
            if ang_diff <= 38.0:
                has_neighbor = True
                break
        if has_neighbor:
            dash_indices.add(idx_a)

    if len(dash_indices) < 6:
        return set()

    centers: Dict[int, Tuple[float, float]] = {idx: (x, y) for idx, x, y, _, _ in candidates}
    if _ring_octant_count(dash_indices, centers, h_roi, w_roi) < 3:
        return set()

    return dash_indices


def _build_barrier_mask(
    contours: List[np.ndarray],
    comb_tick_indices: Set[int],
    dash_indices: Set[int],
    h_roi: int,
    w_roi: int,
) -> np.ndarray:
    """
    Строит маску барьера только из структурных элементов рамки бабла.

    Обычные символы текста внутрь не попадают — иначе мостик рамки
    «съедал» бы столбцы текста и запечатывание ложно срабатывало.
    """
    barrier_mask = np.zeros((h_roi, w_roi), dtype=np.uint8)
    edge_margin = 2
    center_x, center_y = w_roi // 2, h_roi // 2
    comb_nonempty = bool(comb_tick_indices)

    for idx, cnt in enumerate(contours):
        cx, cy, cw, ch = cv2.boundingRect(cnt)
        touches_edge = (
            cx <= edge_margin
            or cy <= edge_margin
            or (cx + cw) >= w_roi - edge_margin
            or (cy + ch) >= h_roi - edge_margin
        )

        # 1) Лучи гребёнки и штрихи пунктирной рамки
        if idx in comb_tick_indices or idx in dash_indices:
            cv2.drawContours(barrier_mask, [cnt], -1, 255, thickness=cv2.FILLED)
            continue

        # 2) Крупные контуры — сама рамка/заливка бабла
        if cw >= w_roi * 0.70 and ch >= h_roi * 0.70:
            cv2.drawContours(barrier_mask, [cnt], -1, 255, thickness=cv2.FILLED)
            continue

        # 3) Контуры, срезанные краем ROI
        if touches_edge:
            is_long = cw >= w_roi * 0.25 or ch >= h_roi * 0.25
            # Если гребёнка найдена, у края могут лежать и короткие срезанные лучи.
            if is_long or comb_nonempty:
                cv2.drawContours(barrier_mask, [cnt], -1, 255, thickness=cv2.FILLED)
                continue

        # 4) Дуги рамки / слипшиеся пучки лучей по периметру
        covers_center = (cx <= center_x <= cx + cw) and (cy <= center_y <= cy + ch)
        bbox_radial = math.hypot(
            (cx + cw * 0.5 - w_roi * 0.5) / max(1.0, w_roi * 0.5),
            (cy + ch * 0.5 - h_roi * 0.5) / max(1.0, h_roi * 0.5),
        )
        if (
            not covers_center
            and max(cw / max(1.0, w_roi), ch / max(1.0, h_roi)) >= 0.28
            and (bbox_radial >= 0.60 or touches_edge)
        ):
            cv2.drawContours(barrier_mask, [cnt], -1, 255, thickness=cv2.FILLED)

    return barrier_mask


def clean_white_bubble_patch(roi: np.ndarray, gray: np.ndarray):
    h_roi, w_roi = roi.shape[:2]
    if h_roi < 3 or w_roi < 3:
        return

    _, dark_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return

    # Базовое белое ядро и контакт с краями ROI — общие для всех веток
    interior_white, border_pixels, perimeter = _build_white_core(gray)

    # Гребёнка радиальных лучей — защищаем всегда, когда найдена
    comb_tick_indices = _detect_border_comb_ticks(contours, h_roi, w_roi)

    # Пунктирную рамку ищем только при утечке белого к краям ROI
    dash_indices: Set[int] = set()
    if border_pixels > perimeter * 0.06:
        dash_indices = _detect_perimeter_dashes(contours, h_roi, w_roi)

    # Барьер строится только из элементов рамки, без символов текста
    barrier_mask = _build_barrier_mask(contours, comb_tick_indices, dash_indices, h_roi, w_roi)

    interior_mask, sealed_by_bridging = _build_bubble_interior_mask(
        gray,
        interior_white,
        border_pixels,
        perimeter,
        barrier_mask,
    )

    # Пунктир защищаем только если замыкание реально запечатало бабл,
    # иначе вертикальные штрихи текста могли бы попасть в защиту.
    protected_indices: Set[int] = set(comb_tick_indices)
    if sealed_by_bridging:
        protected_indices |= dash_indices

    # Предварительно считаем долю каждого контура внутри белого ядра бабла
    inside_ratios: List[float] = []
    for cnt in contours:
        cx, cy, cw, ch = cv2.boundingRect(cnt)
        sub_interior = interior_mask[cy : cy + ch, cx : cx + cw]
        cnt_mask = np.zeros((ch, cw), dtype=np.uint8)
        cv2.fillPoly(cnt_mask, [cnt - [cx, cy]], 255)
        ratio = np.sum((cnt_mask == 255) & (sub_interior == 255)) / float(
            max(1, np.sum(cnt_mask == 255))
        )
        inside_ratios.append(ratio)

    text_clean_mask = np.zeros_like(gray)
    border_mask = np.zeros_like(gray)
    edge_margin = 2

    for idx, cnt in enumerate(contours):
        cx, cy, cw, ch = cv2.boundingRect(cnt)
        touches_edge = (
            cx <= edge_margin
            or cy <= edge_margin
            or (cx + cw) >= w_roi - edge_margin
            or (cy + ch) >= h_roi - edge_margin
        )
        is_large = cw >= w_roi * 0.70 and ch >= h_roi * 0.70

        if is_large or idx in protected_indices:
            cv2.drawContours(border_mask, [cnt], -1, 255, thickness=cv2.FILLED)
            continue

        inside_ratio = inside_ratios[idx]

        if touches_edge:
            is_long = cw >= w_roi * 0.30 or ch >= h_roi * 0.30
            if is_long or inside_ratio < 0.75:
                cv2.drawContours(border_mask, [cnt], -1, 255, thickness=cv2.FILLED)
                continue
        elif inside_ratio < 0.75:
            cv2.drawContours(border_mask, [cnt], -1, 255, thickness=cv2.FILLED)
            continue

        cv2.fillPoly(text_clean_mask, [cnt], 255)

    if np.sum(text_clean_mask) == 0:
        return

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_text = cv2.dilate(text_clean_mask, kernel, iterations=2)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilated_text = cv2.morphologyEx(dilated_text, cv2.MORPH_CLOSE, close_kernel, iterations=1)

    border_shield = cv2.dilate(border_mask, kernel, iterations=1)
    dilated_text[border_shield == 255] = 0
    dilated_text[interior_mask == 0] = 0

    roi[dilated_text == 255] = [255, 255, 255]
