# services/cleaner_ops/stroke_mask.py
# Маска клина текста «Авто-Кисть» (Virtual Brush + Metaballs + Voronoi Gutter Guard):
# символы вместе с их реальной обводкой объединяются в органические мазки круглой кисти
# вдоль потока текста, сглаживаются метаболлами, а коридоры живого фона между столбцами
# (>= 10px) защищаются по биссектрисе Вороного.

import cv2
import numpy as np

from services.cleaner_ops.stroke_cores import (
    extract_polarity_candidates,
    filter_text_components,
    fill_inner_holes,
    grow_halo_around_strokes,
)
from services.cleaner_ops.stroke_capsules import build_capsules, detect_vertical_flow

# --- Параметры алгоритма ---------------------------------------------------------
_OUTER_PAD = 6          # технический пояс вокруг рамки, чтобы видеть пересекающий её лайнарт
_HALO_MAX_PX = 14       # предел геодезического роста по контрастной обводке букв
_HALO_USE_MAX = 10      # на столько максимум расширяем капсулу под обводку
_MARGIN_MIN = 6         # минимальный внешний запас на чистый фон (антиалиасинг обводки)
_MARGIN_MAX = 10
_MIN_SECONDARY_SCORE = 0.5  # насколько второй полярности можно уступать первой


def build_text_stroke_mask(
    image_np: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> np.ndarray:
    """
    Строит маску клина текста для области [y1:y2, x1:x2] на странице image_np.

    Маска — органические мазки «виртуальной кисти» вдоль потока текста (вертикальный
    или горизонтальный столбец/строка символов с наклоном и изгибом), а не фигурный
    трафарет отдельных букв и не осевые прямоугольники: это ровно тот вид маски,
    с которым `anime-manga-big-lama.pt` тянет скринтон без «призрачных» швов.

    Возвращает бинарную маску uint8 (0 или 255) размера (y2 - y1, x2 - x1).
    Если надёжные текстовые штрихи выделить не удалось, возвращает пустую маску.
    """
    img_h, img_w = image_np.shape[:2]
    roi_h, roi_w = y2 - y1, x2 - x1
    if roi_h < 6 or roi_w < 6:
        return np.zeros((max(1, roi_h), max(1, roi_w)), dtype=np.uint8)

    # Берём внешний пояс вокруг рамки, чтобы видеть линии лайнарта, пересекающие границу
    ext_x1 = max(0, x1 - _OUTER_PAD)
    ext_y1 = max(0, y1 - _OUTER_PAD)
    ext_x2 = min(img_w, x2 + _OUTER_PAD)
    ext_y2 = min(img_h, y2 + _OUTER_PAD)

    pad_left = x1 - ext_x1
    pad_top = y1 - ext_y1

    ext_bgr = image_np[ext_y1:ext_y2, ext_x1:ext_x2]
    ext_gray = cv2.cvtColor(ext_bgr, cv2.COLOR_BGR2GRAY)
    roi_gray = ext_gray[pad_top:pad_top + roi_h, pad_left:pad_left + roi_w]

    # Масштаб ядра BlackHat/TopHat под толщину штриха шрифта: два масштаба,
    # чтобы захватить и мелкий текст, и крупные SFX с толстыми штрихами
    min_side = min(roi_h, roi_w)
    bh_k = max(9, min(25, int(min_side * 0.18) | 1))
    kernel_sizes = [bh_k, min(41, bh_k * 2 + 1)]

    # Проверяем обе полярности (тёмные буквы и белые буквы) и выбираем лучшую
    dark_cand = extract_polarity_candidates(ext_gray, "dark", kernel_sizes)
    dark_core, dark_score = filter_text_components(dark_cand, pad_top, pad_left, roi_h, roi_w)

    light_cand = extract_polarity_candidates(ext_gray, "light", kernel_sizes)
    light_core, light_score = filter_text_components(light_cand, pad_top, pad_left, roi_h, roi_w)

    # Если медианный фон тёмный (< 105) и светлые буквы набрали хороший балл — берём 'light'
    median_bg = float(np.median(roi_gray))
    if median_bg < 105.0 and light_score >= dark_score * 0.75 and light_score > 0:
        primary = (light_core, "light", light_score)
        secondary = (dark_core, "dark", dark_score)
    elif dark_score >= light_score and dark_score > 0:
        primary = (dark_core, "dark", dark_score)
        secondary = (light_core, "light", light_score)
    elif light_score > 0:
        primary = (light_core, "light", light_score)
        secondary = (dark_core, "dark", dark_score)
    else:
        return np.zeros((roi_h, roi_w), dtype=np.uint8)

    # В одной рамке бывает и обычный тёмный текст, и выворотный (белые буквы с
    # контуром, SFX): вторую полярность добавляем, если она набрала сопоставимый балл
    polarities = [primary[:2]]
    if secondary[2] >= primary[2] * _MIN_SECONDARY_SCORE and np.count_nonzero(secondary[0]) >= 12:
        polarities.append(secondary[:2])

    # Внешний запас на чистый фон поверх обводки (антиалиасинг + запас LaMa)
    outward = int(np.clip(round(min_side * 0.02), _MARGIN_MIN, _MARGIN_MAX))

    filled_cores = [(fill_inner_holes(core), polarity) for core, polarity in polarities]
    union_core = np.zeros((roi_h, roi_w), dtype=np.uint8)
    for core, _ in filled_cores:
        union_core = cv2.bitwise_or(union_core, core)
    vertical_flow = detect_vertical_flow(union_core, roi_h, roi_w)

    capsule_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    for core, polarity in filled_cores:
        # Полный захват контрастной обводки: реальная выращенная маска (с залитыми
        # полостями) уходит в построение узлов, чтобы кисть обтягивала «буква + кант».
        grown, halo_px = grow_halo_around_strokes(
            roi_gray, core, polarity, max_halo_px=_HALO_MAX_PX
        )
        grown_filled = fill_inner_holes(grown)
        halo_px = min(halo_px, _HALO_USE_MAX)

        # Слияние символов виртуальной кистью по оси чтения
        # (для горизонтального текста — на транспонированной маске)
        if vertical_flow:
            part = build_capsules(
                core, roi_w, roi_h, halo_px, outward, grown_mask=grown_filled
            )
        else:
            transposed = build_capsules(
                cv2.transpose(core),
                roi_h,
                roi_w,
                halo_px,
                outward,
                grown_mask=cv2.transpose(grown_filled),
            )
            part = cv2.transpose(transposed)
        capsule_mask = cv2.bitwise_or(capsule_mask, part)

    if not np.any(capsule_mask):
        return np.zeros((roi_h, roi_w), dtype=np.uint8)

    return capsule_mask
