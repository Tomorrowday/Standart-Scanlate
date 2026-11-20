# services/cleaner_ops/brush_unet_mask.py
# U-Net-маска текста для клина Free-Text (класс 2): препроцессинг 4-канального входа,
# инференс TorchScript-модели из weights/brush и постпроцессинг в маску рамки.
#
# Контракт модели (менять нельзя):
#   вход  — (1, 4, H, W) float [0..1], H/W кратны 32, канал 3 — box prior (1 внутри рамки);
#   выход — (1, 1, H, W) вероятности [0..1] (sigmoid и ImageNet-нормализация уже внутри графа).
# Снаружи нормализацию применять нельзя.

import math
from typing import Any, Dict, Tuple

import cv2
import numpy as np
import torch

from config import BRUSH_SIZE_MULTIPLE, DEFAULT_BRUSH_MAX_SIDE
from logger import logger
from ml.models import ml


def compute_pad(box_w: int, box_h: int) -> int:
    """Контекстный запас вокруг рамки: pad = max(24, int(max(bw, bh) * 0.15))."""
    return int(max(24, int(max(box_w, box_h) * 0.15)))


def make_box_prior(crop_shape: Tuple[int, int], box_local) -> np.ndarray:
    """
    Канал 3 (Box Prior): 1.0 внутри целевой рамки в координатах кропа, 0.0 снаружи.
    crop_shape — (h, w) кропа; box_local — (x1, y1, x2, y2) в координатах кропа.
    """
    h, w = crop_shape[:2]
    prior = np.zeros((h, w), dtype=np.float32)
    x1, y1, x2, y2 = box_local
    x1 = int(max(0, min(w, round(x1))))
    y1 = int(max(0, min(h, round(y1))))
    x2 = int(max(0, min(w, round(x2))))
    y2 = int(max(0, min(h, round(y2))))
    if x2 > x1 and y2 > y1:
        prior[y1:y2, x1:x2] = 1.0
    return prior


def _reflect_pad(arr: np.ndarray, top: int, bottom: int, left: int, right: int) -> np.ndarray:
    """BORDER_REFLECT_101 для RGB; np.pad корректно работает и при паддинге больше кропа."""
    if top == bottom == left == right == 0:
        return arr
    pad_width = [(top, bottom), (left, right)] + ([(0, 0)] if arr.ndim == 3 else [])
    return np.pad(arr, pad_width, mode="reflect")


def prepare_tensor(
    crop_rgb: np.ndarray,
    prior: np.ndarray,
    max_side: int = DEFAULT_BRUSH_MAX_SIDE,
) -> Tuple[torch.Tensor, Dict[str, Any]]:
    """
    Готовит вход (1, 4, H, W) со значениями [0..1] в режиме infer.

    Без апскейла: если max(h, w) > max_side — пропорциональный ресайз (RGB — INTER_AREA,
    prior — INTER_NEAREST), иначе масштаб 1.0. Затем паддинг до ближайшего кратного 32
    с центрированием: RGB — reflect, prior — нули.

    Возвращает тензор и meta для restore_mask().
    """
    h, w = crop_rgb.shape[:2]

    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        rs_w = max(1, int(round(w * scale)))
        rs_h = max(1, int(round(h * scale)))
        rgb_r = cv2.resize(crop_rgb, (rs_w, rs_h), interpolation=cv2.INTER_AREA)
        prior_r = cv2.resize(prior.astype(np.float32), (rs_w, rs_h), interpolation=cv2.INTER_NEAREST)
    else:
        scale = 1.0
        rs_w, rs_h = w, h
        rgb_r, prior_r = crop_rgb, prior.astype(np.float32)

    mult = BRUSH_SIZE_MULTIPLE
    out_w = int(math.ceil(rs_w / mult) * mult)
    out_h = int(math.ceil(rs_h / mult) * mult)

    pad_total_x = out_w - rs_w
    pad_total_y = out_h - rs_h
    left = pad_total_x // 2
    top = pad_total_y // 2
    right = pad_total_x - left
    bottom = pad_total_y - top

    rgb_p = _reflect_pad(rgb_r.astype(np.uint8), top, bottom, left, right)
    prior_p = np.pad(prior_r.astype(np.float32), ((top, bottom), (left, right)), mode="constant")

    # Никакой нормализации ImageNet: она уже внутри TorchScript-графа.
    rgb_f = rgb_p.astype(np.float32) / 255.0
    stacked = np.concatenate([rgb_f, prior_p[:, :, None]], axis=2)  # (H, W, 4)
    tensor = torch.from_numpy(np.ascontiguousarray(stacked.transpose(2, 0, 1))).unsqueeze(0).float()

    meta = {
        "scale": float(scale),
        "crop_w": int(w),
        "crop_h": int(h),
        "resized_w": int(rs_w),
        "resized_h": int(rs_h),
        "out_w": int(out_w),
        "out_h": int(out_h),
        "pad_left": int(left),
        "pad_top": int(top),
    }
    return tensor, meta


def restore_mask(pred: torch.Tensor, meta: Dict[str, Any], threshold: float = 0.5) -> np.ndarray:
    """
    Возвращает маску предсказания в размере исходного кропа (uint8 0/255).
    pred — тензор (1, 1, H, W) или (1, H, W) с вероятностями [0..1].
    """
    if isinstance(pred, torch.Tensor):
        arr = pred.detach().float().cpu().numpy()
    else:
        arr = np.asarray(pred, dtype=np.float32)
    while arr.ndim > 2:
        arr = arr[0]

    left, top = meta["pad_left"], meta["pad_top"]
    rs_w, rs_h = meta["resized_w"], meta["resized_h"]
    crop = arr[top:top + rs_h, left:left + rs_w]

    if crop.shape[1] != meta["crop_w"] or crop.shape[0] != meta["crop_h"]:
        crop = cv2.resize(crop, (meta["crop_w"], meta["crop_h"]), interpolation=cv2.INTER_LINEAR)

    return ((crop >= threshold).astype(np.uint8)) * 255


def apply_morphology(mask: np.ndarray, extra_dilate_px: int) -> np.ndarray:
    """Расширяет (r > 0) или эродирует (r < 0) маску круглым ядром 2r+1. 0 — без изменений."""
    r = int(extra_dilate_px)
    if r == 0:
        return mask
    radius = abs(r)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    op = cv2.MORPH_DILATE if r > 0 else cv2.MORPH_ERODE
    return cv2.morphologyEx(mask, op, kernel)


def predict_text_brush_mask(
    image_np: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    model_name: str,
    threshold: float = 0.5,
    extra_dilate: int = 0,
    max_side: int = DEFAULT_BRUSH_MAX_SIDE,
) -> np.ndarray:
    """
    Строит нейросетевую маску мазка текста внутри рамки [x1:x2, y1:y2].

    Возвращает uint8-маску 0/255 размером с рамку (U-Net не мажет контекст: из маски
    кропа вырезается только сама рамка). Любая ошибка → пустая маска + warning,
    чтобы модель не роняла клин страницы (вызывающий откатится на OpenCV).
    """
    bw = int(max(0, x2 - x1))
    bh = int(max(0, y2 - y1))
    empty = np.zeros((bh, bw), dtype=np.uint8)
    if bw <= 0 or bh <= 0:
        return empty

    try:
        img_h, img_w = image_np.shape[:2]
        pad = compute_pad(bw, bh)
        cx1 = max(0, int(x1) - pad)
        cy1 = max(0, int(y1) - pad)
        cx2 = min(img_w, int(x2) + pad)
        cy2 = min(img_h, int(y2) + pad)

        crop_bgr = image_np[cy1:cy2, cx1:cx2]
        if crop_bgr.size == 0:
            return empty

        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        box_local = (x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1)
        prior = make_box_prior(crop_rgb.shape[:2], box_local)

        tensor, meta = prepare_tensor(crop_rgb, prior, max_side=max_side)

        wrapper = ml.load_brush(model_name)
        pred = wrapper.predict(tensor)

        crop_mask = restore_mask(pred, meta, threshold=threshold)

        ox, oy = int(x1) - cx1, int(y1) - cy1
        mask = crop_mask[oy:oy + bh, ox:ox + bw]
        if mask.shape != (bh, bw):
            mask = cv2.resize(mask, (bw, bh), interpolation=cv2.INTER_NEAREST)

        return apply_morphology(np.ascontiguousarray(mask), extra_dilate)
    except Exception as e:
        logger.warning(f"U-Net-маска текста недоступна ({model_name}): {e}. Откат на OpenCV.")
        return empty


__all__ = [
    "compute_pad",
    "make_box_prior",
    "prepare_tensor",
    "restore_mask",
    "apply_morphology",
    "predict_text_brush_mask",
]
