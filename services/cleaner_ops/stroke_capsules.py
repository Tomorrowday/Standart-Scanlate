# services/cleaner_ops/stroke_capsules.py
# Алгоритм «Виртуальная Кисть» (Virtual Brush + Metaballs + Voronoi Gutter Guard):
# имитирует движение круглой кисти человека по цепочкам символов с сохранением
# живых коридоров скринтона между соседними столбцами/строками.

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

# Минимальная ширина живого коридора фона между столбцами, который нельзя затирать
MIN_GUTTER_PX = 10
# Узкие просветы меньше этого порога плавно сливаются в единый мазок
MERGE_GAP_PX = 8


@dataclass
class _GlyphNode:
    cx: float
    cy: float
    x1: int
    y1: int
    x2: int
    y2: int
    w: int
    h: int
    area: int
    radius: float
    hull: Optional[np.ndarray]


def detect_vertical_flow(core_mask: np.ndarray, roi_h: int, roi_w: int) -> bool:
    """
    Определяет преимущественную ориентацию текста по взаимному расположению символов:
    у вертикального столбца ближайший сосед находится сверху/снизу (|dy| > |dx|),
    у горизонтальной строки — слева/справа.
    """
    radius = int(np.clip(round(min(roi_h, roi_w) * 0.02), 2, 6))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    merged = cv2.dilate(core_mask, kernel, iterations=1)

    num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(merged, connectivity=8)
    centers = [
        (float(centroids[lbl][0]), float(centroids[lbl][1]))
        for lbl in range(1, num_labels)
        if stats[lbl, cv2.CC_STAT_AREA] >= 12
    ]
    if len(centers) < 3:
        return roi_h >= roi_w

    vertical_votes = 0
    total = 0
    for i, (cx, cy) in enumerate(centers):
        best_dist = None
        nearest = None
        for j, (ox, oy) in enumerate(centers):
            if i == j:
                continue
            dist = (ox - cx) ** 2 + (oy - cy) ** 2
            if best_dist is None or dist < best_dist:
                best_dist, nearest = dist, (ox, oy)
        if nearest is None or best_dist == 0:
            continue
        dx = abs(nearest[0] - cx)
        dy = abs(nearest[1] - cy)
        total += 1
        if dy > dx:
            vertical_votes += 1

    if total == 0:
        return roi_h >= roi_w

    ratio = vertical_votes / float(total)
    if 0.35 <= ratio <= 0.65:
        return roi_h >= roi_w
    return ratio > 0.5


def _draw_capsule_between_circles(
    canvas: np.ndarray,
    x1: float,
    y1: float,
    r1: float,
    x2: float,
    y2: float,
    r2: float,
) -> None:
    """
    Рисует гладкую тангенциальную капсулу между двумя кругами (x1, y1, r1) и (x2, y2, r2)
    как выпуклую оболочку точек обеих окружностей (аналог мазка круглой кистью переменного нажима).
    """
    angles = np.linspace(0.0, 2.0 * np.pi, 20, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    pts1 = np.column_stack((x1 + r1 * cos_a, y1 + r1 * sin_a))
    pts2 = np.column_stack((x2 + r2 * cos_a, y2 + r2 * sin_a))
    all_pts = np.vstack((pts1, pts2)).round().astype(np.int32)

    hull = cv2.convexHull(all_pts)
    cv2.fillConvexPoly(canvas, hull, 255, lineType=cv2.LINE_AA)


def _smooth_as_metaball(mask: np.ndarray, blur_radius: int) -> np.ndarray:
    """
    Превращает маску в гладкий «мазок кисти» без углов (эффект 2D-метаболлов):
    размытие по Гауссу + отсечение по уровню сглаживает любые зубцы контура.
    """
    r = max(3, int(blur_radius))
    ksize = 2 * r + 1
    blurred = cv2.GaussianBlur(mask, (ksize, ksize), sigmaX=r * 0.55, sigmaY=r * 0.55)
    return ((blurred >= 112).astype(np.uint8)) * 255


def _extract_glyph_nodes(
    core_mask: np.ndarray,
    ink_mask: np.ndarray,
    cross_len: int,
    along_len: int,
) -> List[_GlyphNode]:
    """
    Группирует близкие штрихи одного иероглифа в узлы символов (_GlyphNode)
    и вычисляет для каждого узла выпуклую оболочку его пикселей вместе с обводкой (ink_mask).
    """
    min_side = min(cross_len, along_len)
    rx = int(np.clip(round(min_side * 0.014), 2, 4))
    ry = int(np.clip(round(min_side * 0.020), 2, 5))
    merge_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rx + 1, 2 * ry + 1))
    glyph_blobs = cv2.dilate(core_mask, merge_k, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(glyph_blobs, connectivity=8)
    nodes: List[_GlyphNode] = []

    for lbl in range(1, num_labels):
        gx = int(stats[lbl, cv2.CC_STAT_LEFT])
        gy = int(stats[lbl, cv2.CC_STAT_TOP])
        gw = int(stats[lbl, cv2.CC_STAT_WIDTH])
        gh = int(stats[lbl, cv2.CC_STAT_HEIGHT])

        # Игнорируем случайную длинную тонкую поперечную линию (осколок рамки фрейма)
        if gw >= cross_len * 0.68 and gw > 3.0 * gh:
            continue

        sub_lbl = labels[gy : gy + gh, gx : gx + gw] == lbl
        sub_core = (core_mask[gy : gy + gh, gx : gx + gw] > 0) & sub_lbl
        core_area = int(np.count_nonzero(sub_core))
        if core_area < 6:
            continue

        # Берём пиксели с учётом обводки (ink_mask) в окрестности данного символа
        sub_ink = (ink_mask[gy : gy + gh, gx : gx + gw] > 0) & sub_lbl
        if not np.any(sub_ink):
            sub_ink = sub_core

        ys, xs = np.nonzero(sub_ink)
        abs_xs = xs + gx
        abs_ys = ys + gy

        x1, x2 = int(abs_xs.min()), int(abs_xs.max()) + 1
        y1, y2 = int(abs_ys.min()), int(abs_ys.max()) + 1
        w = max(2, x2 - x1)
        h = max(2, y2 - y1)
        cx = float(abs_xs.mean())
        cy = float(abs_ys.mean())

        pts = np.column_stack((abs_xs, abs_ys)).astype(np.int32)
        hull = cv2.convexHull(pts) if len(pts) >= 3 else None

        # Базовый радиус кисти для узла — половина поперечного габарита символа с обводкой
        radius = max(3.5, min(w, h) * 0.5, w * 0.46)
        nodes.append(
            _GlyphNode(
                cx=cx,
                cy=cy,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                w=w,
                h=h,
                area=core_area,
                radius=radius,
                hull=hull,
            )
        )

    return nodes


def _build_stroke_chains(
    nodes: List[_GlyphNode],
) -> Tuple[List[List[int]], List[Tuple[int, int]]]:
    """
    Соединяет символы в цепочки мазков вдоль вертикальной оси чтения.
    Допускает плавный наклон и изгиб текста, но не перепрыгивает через межстолбцовый коридор.
    Возвращает (список цепочек индексов узлов, список направленных рёбер (u, v)).
    """
    n = len(nodes)
    if n == 0:
        return [], []
    if n == 1:
        return [[0]], []

    order = sorted(range(n), key=lambda idx: (nodes[idx].cy, nodes[idx].cx))
    glyph_h = max(8.0, float(np.percentile([nd.h for nd in nodes], 70)))
    glyph_w = max(8.0, float(np.percentile([nd.w for nd in nodes], 70)))

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edges: List[Tuple[int, int]] = []
    # Для каждого узла ищем лучшего соседа сверху и лучшего соседа снизу в том же столбце
    max_gap_y = max(18.0, glyph_h * 1.45)

    for pos, i in enumerate(order):
        ni = nodes[i]
        best_prev: Optional[int] = None
        best_cost = float("inf")

        for prev_pos in range(pos - 1, -1, -1):
            p = order[prev_pos]
            np_node = nodes[p]

            gap_y = float(ni.y1 - np_node.y2)
            if gap_y > max_gap_y:
                continue

            overlap_x = float(min(ni.x2, np_node.x2) - max(ni.x1, np_node.x1))
            dx = abs(ni.cx - np_node.cx)
            ref_w = max(float(ni.w), float(np_node.w), glyph_w)

            # Символы лежат на одной линии кисти, если перекрываются по X
            # или смещены по X не более чем на 62% ширины символа (наклонный текст/SFX)
            if overlap_x < -2.0 and dx > ref_w * 0.62:
                continue

            cost = max(0.0, gap_y) + dx * 1.85
            if cost < best_cost:
                best_cost = cost
                best_prev = p

        if best_prev is not None:
            union(best_prev, i)
            edges.append((best_prev, i))

    groups_map: dict[int, List[int]] = {}
    for idx in range(n):
        groups_map.setdefault(find(idx), []).append(idx)

    raw_chains = list(groups_map.values())
    if len(raw_chains) <= 1:
        return raw_chains, edges

    # Отсеиваем только совсем мелкие изолированные точки-шум далеко от основного текста,
    # но СОХРАНЯЕМ короткие столбцы (даже из 1–2 иероглифов или знаков !?)
    chain_areas = [sum(nodes[i].area for i in ch) for ch in raw_chains]
    max_chain_area = max(chain_areas) if chain_areas else 0

    kept_chains: List[List[int]] = []
    for ch, ch_area in zip(raw_chains, chain_areas):
        if len(ch) >= 2 or ch_area >= 20 or ch_area >= max_chain_area * 0.08:
            kept_chains.append(ch)
            continue
        # Одиночный мелкий компонент оставляем, если он рядом с любой крупной цепочкой (например, точка/дакутэн)
        nd = nodes[ch[0]]
        near_other = any(
            abs(nd.cx - nodes[o].cx) <= glyph_w * 1.6 and abs(nd.cy - nodes[o].cy) <= glyph_h * 1.6
            for other_ch in raw_chains
            if other_ch is not ch and (len(other_ch) >= 2 or sum(nodes[k].area for k in other_ch) >= 20)
            for o in other_ch
        )
        if near_other:
            kept_chains.append(ch)

    kept_set = {idx for ch in kept_chains for idx in ch}
    kept_edges = [(u, v) for u, v in edges if u in kept_set and v in kept_set]
    return kept_chains, kept_edges


def _paint_chain_brush(
    shape: Tuple[int, int],
    nodes: List[_GlyphNode],
    chain: List[int],
    chain_edges: List[Tuple[int, int]],
    halo_px: int,
) -> np.ndarray:
    """
    Рисует базовый мазок кисти (ядро + обводка) для одной цепочки символов:
    выпуклые оболочки символов + круглые штампы кисти + гладкие капсулы переходов.
    """
    canvas = np.zeros(shape, dtype=np.uint8)
    if not chain:
        return canvas

    med_radius = float(np.median([nodes[i].radius for i in chain]))
    # Не даём кисти сильно сужаться на мелкой кане (っ, ー, 、) внутри столбца
    effective_radii = {
        i: float(max(nodes[i].radius, med_radius * 0.76)) + float(halo_px)
        for i in chain
    }

    for i in chain:
        nd = nodes[i]
        if nd.hull is not None:
            cv2.fillConvexPoly(canvas, nd.hull, 255, lineType=cv2.LINE_AA)
        r_int = max(2, int(round(effective_radii[i])))
        cv2.circle(canvas, (int(round(nd.cx)), int(round(nd.cy))), r_int, 255, -1, lineType=cv2.LINE_AA)

    for u, v in chain_edges:
        nu, nv = nodes[u], nodes[v]
        _draw_capsule_between_circles(
            canvas,
            nu.cx,
            nu.cy,
            effective_radii[u],
            nv.cx,
            nv.cy,
            effective_radii[v],
        )
        if nu.hull is not None and nv.hull is not None:
            joint_pts = np.vstack((nu.hull.reshape(-1, 2), nv.hull.reshape(-1, 2)))
            joint_hull = cv2.convexHull(joint_pts)
            cv2.fillConvexPoly(canvas, joint_hull, 255, lineType=cv2.LINE_AA)

    if halo_px > 0:
        hk = 2 * int(halo_px) + 1
        h_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (hk, hk))
        canvas = cv2.dilate(canvas, h_kernel, iterations=1)

    return canvas


def _expand_with_voronoi_gutters(
    chain_masks: List[np.ndarray],
    outward_px: int,
) -> np.ndarray:
    """
    Расширяет мазки кисти на внешний запас outward_px со сглаживанием метаболлами,
    сохраняя живой коридор фона (>= MIN_GUTTER_PX) между соседними столбцами
    по биссектрисе Вороного.
    """
    if not chain_masks:
        return np.zeros((1, 1), dtype=np.uint8)

    h, w = chain_masks[0].shape[:2]
    out_r = max(2, int(outward_px))
    out_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * out_r + 1, 2 * out_r + 1))

    if len(chain_masks) == 1:
        expanded = cv2.dilate(chain_masks[0], out_kernel, iterations=1)
        smoothed = _smooth_as_metaball(expanded, blur_radius=out_r)
        return cv2.bitwise_or(smoothed, chain_masks[0])

    # Расстояния от базового мазка (буквы + обводка) каждой цепочки
    dists: List[np.ndarray] = []
    expanded_list: List[np.ndarray] = []
    for cm in chain_masks:
        dist = cv2.distanceTransform((cm == 0).astype(np.uint8), cv2.DIST_L2, 5)
        dists.append(dist)
        exp = cv2.dilate(cm, out_kernel, iterations=1)
        sm = _smooth_as_metaball(exp, blur_radius=out_r)
        expanded_list.append(cv2.bitwise_or(sm, cm))

    combined = np.zeros((h, w), dtype=np.uint8)
    for exp in expanded_list:
        combined = cv2.bitwise_or(combined, exp)

    # Проверяем каждую пару цепочек: если между их обводками есть живой коридор >= MIN_GUTTER_PX,
    # защищаем середину коридора (биссектрису Вороного) от слияния при расширении на outward_px
    gutter_carve = np.zeros((h, w), dtype=bool)
    num_chains = len(chain_masks)

    # Предрасчёт точек и bbox цепочек: bbox нужен для дешёвого отсева далёких пар,
    # иначе биссектриса Вороного между 0-й и 2-й цепочкой проходит через средний столбец.
    chain_pts: List[np.ndarray] = []
    chain_bboxes: List[Optional[Tuple[int, int, int, int]]] = []
    chain_union = np.zeros((h, w), dtype=bool)
    for cm in chain_masks:
        pts = cm > 0
        chain_pts.append(pts)
        if np.any(pts):
            ys, xs = np.where(pts)
            chain_bboxes.append((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
        else:
            chain_bboxes.append(None)
        chain_union |= pts

    # Пара может физически слиться только на таком расстоянии; дальние цепочки
    # (например, столбцы 0 и 2 через столбец 1) не должны вырезать чужой центр.
    max_merge_gap = 2.0 * out_r + MERGE_GAP_PX + 6.0

    for i in range(num_chains):
        if not np.any(chain_pts[i]):
            continue
        bi = chain_bboxes[i]
        for j in range(i + 1, num_chains):
            if not np.any(chain_pts[j]):
                continue
            bj = chain_bboxes[j]
            if bi is None or bj is None:
                continue

            # Дешёвый предфильтр по bbox (расширяем на максимально возможный зазор)
            if (bi[0] - max_merge_gap > bj[2] or bj[0] - max_merge_gap > bi[2] or
                    bi[1] - max_merge_gap > bj[3] or bj[1] - max_merge_gap > bi[3]):
                continue

            min_gap = float(np.min(dists[i][chain_pts[j]]))
            if not (MIN_GUTTER_PX <= min_gap <= max_merge_gap):
                continue

            # Середина коридора между цепочками i и j
            di, dj = dists[i], dists[j]
            mid_corridor = (
                (np.abs(di - dj) < (MIN_GUTTER_PX * 0.5))
                & (di > 1.0)
                & (dj > 1.0)
                & ((di + dj) <= (min_gap + 2.0 * out_r + 8.0))
            )
            gutter_carve |= mid_corridor

    # Базовая маска самих штрихов неприкосновенна: коридор не должен выгрызать буквы.
    gutter_carve &= ~chain_union

    if np.any(gutter_carve):
        combined[gutter_carve] = 0
        # Скругляем края после подрезки коридора
        round_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, round_k)
        for cm in chain_masks:
            combined = cv2.bitwise_or(combined, cm)

    # Узкие просветы (< MERGE_GAP_PX), где не сработала защита коридора, плавно закрываем
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MERGE_GAP_PX + 1, MERGE_GAP_PX + 1))
    closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, close_k)
    if np.any(gutter_carve):
        closed[gutter_carve] = 0
        # MORPH_CLOSE мог снова затянуть коридор — восстанавливаем штрихи после финальной подрезки
        for cm in chain_masks:
            closed = cv2.bitwise_or(closed, cm)

    return closed


def build_capsules(
    core_mask: np.ndarray,
    cross_len: int,
    along_len: int,
    halo_px: int,
    outward_px: int,
    grown_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Строит маску «Виртуальной Кисти» вдоль вертикальной оси маски:
    объединяет символы в органические мазки кисти по траектории текста,
    захватывает реальную обводку (grown_mask) и сохраняет живые коридоры между столбцами.
    """
    canvas = np.zeros(core_mask.shape, dtype=np.uint8)
    if not np.any(core_mask):
        return canvas

    ink_mask = grown_mask if (grown_mask is not None and np.any(grown_mask)) else core_mask
    nodes = _extract_glyph_nodes(core_mask, ink_mask, cross_len, along_len)
    if not nodes:
        return canvas

    chains, all_edges = _build_stroke_chains(nodes)
    if not chains:
        return canvas

    # Если grown_mask уже передана, основная часть обводки уже внутри узлов;
    # добавляем небольшой остаточный запас (2px) на сглаживание краёв ореола
    extra_halo = 2 if (grown_mask is not None and halo_px > 0) else int(halo_px)

    chain_masks: List[np.ndarray] = []
    for ch in chains:
        ch_set = set(ch)
        ch_edges = [(u, v) for u, v in all_edges if u in ch_set and v in ch_set]
        cm = _paint_chain_brush(core_mask.shape[:2], nodes, ch, ch_edges, extra_halo)
        if np.any(cm):
            chain_masks.append(cm)

    if not chain_masks:
        return canvas

    return _expand_with_voronoi_gutters(chain_masks, outward_px)
