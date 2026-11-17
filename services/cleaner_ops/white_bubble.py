# services/cleaner_ops/white_bubble.py
# Морфологическая очистка белых речевых баблов (с защитой лучистых/пунктирных рамок)

import math
from typing import List, Set
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


def _build_bubble_interior_mask(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    _, white_canvas = cv2.threshold(gray, 215, 255, cv2.THRESH_BINARY)
    kernel_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded_white = cv2.erode(white_canvas, kernel_3, iterations=1)

    interior_white = _extract_center_white_component(eroded_white, h, w)

    # Если у бабла пунктирная/лучистая рамка, белая заливка просачивается сквозь зазоры
    # между штрихами к краям ROI. Проверяем контакт с границами ROI:
    border_pixels = (
        np.sum(interior_white[0, :] > 0)
        + np.sum(interior_white[-1, :] > 0)
        + np.sum(interior_white[:, 0] > 0)
        + np.sum(interior_white[:, -1] > 0)
    )
    perimeter = 2 * (h + w)

    if border_pixels > perimeter * 0.06:
        # Временно смыкаем соседние лучи (эрозия белого на ширину зазора между лучами)
        gap_k = max(7, min(15, int(min(h, w) * 0.05) | 1))
        bridging_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap_k, gap_k))
        bridged_white = cv2.erode(white_canvas, bridging_kernel, iterations=1)
        sealed_core = _extract_center_white_component(bridged_white, h, w)

        if np.sum(sealed_core > 0) >= (h * w) * 0.06:
            # Слегка возвращаем размер ядра, но оставляем лучи за пределами чистого ядра
            restore_k = max(3, gap_k - 4) | 1
            restore_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (restore_k, restore_k))
            interior_white = cv2.dilate(sealed_core, restore_kernel, iterations=1)
            interior_white = cv2.bitwise_and(interior_white, eroded_white)

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

    return interior_mask


def _detect_border_comb_ticks(
    contours: List[np.ndarray],
    inside_ratios: List[float],
    h_roi: int,
    w_roi: int,
) -> Set[int]:
    """
    Находит индексы контуров, образующих «гребёнку» радиальных лучей по периметру бабла.
    Одиночные штрихи букв (!, は, い, 不) внутри белого поля сюда НЕ попадают, потому что:
      1) они лежат целиком внутри белого ядра (inside_ratio >= 0.88) и далеко от рамки ROI;
      2) у них нет соседних параллельных зубцов гребёнки вдоль границы бабла.
    """
    candidates = []
    min_dim = float(min(h_roi, w_roi))

    for idx, cnt in enumerate(contours):
        if len(cnt) < 4:
            continue

        cx, cy, cw, ch = cv2.boundingRect(cnt)
        # Слишком крупные контуры обрабатываются отдельно
        if cw > w_roi * 0.35 or ch > h_roi * 0.35:
            continue

        (mcx, mcy), (mw, mh), angle = cv2.minAreaRect(cnt)
        long_side = max(mw, mh)
        short_side = max(1.0, min(mw, mh))
        aspect = long_side / short_side

        # Луч должен быть вытянутым штрихом
        if aspect < 2.2 or long_side < 4.0:
            continue

        # Расстояние от центра штриха до ближайшего края ROI
        dist_to_roi_edge = min(mcx, w_roi - mcx, mcy, h_roi - mcy)
        near_roi_edge = dist_to_roi_edge <= max(18.0, min_dim * 0.14)

        # Нормализованный радиус от центра бабла (0 в центре, ~1 у краёв)
        nx = (mcx - w_roi * 0.5) / max(1.0, w_roi * 0.5)
        ny = (mcy - h_roi * 0.5) / max(1.0, h_roi * 0.5)
        radial_dist = math.hypot(nx, ny)

        # КРИТИЧЕСКОЕ ПРАВИЛО: если штрих целиком внутри белого ядра (inside_ratio >= 0.88)
        # и не прижат к самому краю ROI — это буква или знак препинания (!, い, は), а НЕ луч!
        if inside_ratios[idx] >= 0.88 and not near_roi_edge:
            continue

        # Даже у края отсекаем всё, что ближе 0.68 радиуса к центру
        if radial_dist < 0.68 and not near_roi_edge:
            continue

        # Ориентация главной оси штриха в градусах [0..180)
        theta_deg = (angle if mw >= mh else angle + 90.0) % 180.0
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

    return tick_indices


def clean_white_bubble_patch(roi: np.ndarray, gray: np.ndarray):
    h_roi, w_roi = roi.shape[:2]
    if h_roi < 3 or w_roi < 3:
        return

    interior_mask = _build_bubble_interior_mask(gray)
    _, dark_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return

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

    # Находим гребёнку лучей по периметру бабла
    comb_tick_indices = _detect_border_comb_ticks(contours, inside_ratios, h_roi, w_roi)

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

        if is_large or idx in comb_tick_indices:
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
