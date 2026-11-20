# services/cleaner_ops/lama_inpaint.py
# Нейросетевой клин LaMa и сглаженное вклеивание патчей

import math
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import torch

from ml.models import ml
from config import LAMA_FORCE_GRAYSCALE, MAX_LAMA_DIM

from services.cleaner_ops.image_io import is_patch_monochrome
from services.cleaner_ops.white_bubble import _create_shape_mask

# Жёсткий предохранитель от OOM: гигантский локальный кроп сжимается до этого размера
# на время инференса. Поскольку blend_inpainted_patch вклеивает результат только по
# узкой маске, окружающий арт не теряет резкости.
LAMA_HARD_SAFE_DIM = 1600


def inpaint_patch_with_lama(
    patch_bgr: np.ndarray,
    mask: np.ndarray,
    clean_model_name: str = "",
    downscale: bool = False,
) -> np.ndarray:
    """
    Инпейнт патча LaMa.

    downscale передаётся явным аргументом из настроек запроса, а не через
    глобальное ml.lama_downscale: параллельные запросы не перетирают друг другу
    режим качества.
    """
    model = ml.load_cleaner(clean_model_name)
    if model is None:
        return patch_bgr

    h, w = patch_bgr.shape[:2]
    max_dim = max(h, w)

    need_downscale = (
        (downscale and (max_dim > MAX_LAMA_DIM))
        or (max_dim > LAMA_HARD_SAFE_DIM)
    )
    limit_dim = min(MAX_LAMA_DIM, LAMA_HARD_SAFE_DIM) if downscale else LAMA_HARD_SAFE_DIM
    if need_downscale:
        scale_factor = limit_dim / float(max_dim)
        proc_w = max(16, int(round(w * scale_factor)))
        proc_h = max(16, int(round(h * scale_factor)))
        proc_patch = cv2.resize(patch_bgr, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
        proc_mask = cv2.resize(mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
    else:
        proc_patch = patch_bgr
        proc_mask = mask

    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_mask = cv2.dilate(proc_mask, dilate_kernel, iterations=1)

    crop_pil = Image.fromarray(cv2.cvtColor(proc_patch, cv2.COLOR_BGR2RGB))
    mask_pil = Image.fromarray(dilated_mask)

    with torch.inference_mode():
        inpainted_pil = model(crop_pil, mask_pil)

    inpainted_bgr = cv2.cvtColor(np.array(inpainted_pil), cv2.COLOR_RGB2BGR)

    if inpainted_bgr.shape[:2] != (h, w):
        inpainted_bgr = cv2.resize(inpainted_bgr, (w, h), interpolation=cv2.INTER_LANCZOS4)

    if LAMA_FORCE_GRAYSCALE or is_patch_monochrome(patch_bgr):
        inpainted_gray = cv2.cvtColor(inpainted_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(inpainted_gray, cv2.COLOR_GRAY2BGR)

    return inpainted_bgr


def blend_inpainted_patch(
    target_img: np.ndarray,
    inpainted_patch: np.ndarray,
    clean_mask: np.ndarray,
    x1: int, y1: int, x2: int, y2: int
):
    roi_orig = target_img[y1:y2, x1:x2].astype(np.float32)
    roi_inp = inpainted_patch.astype(np.float32)

    dilated = cv2.dilate(clean_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
    feathered = cv2.GaussianBlur(dilated.astype(np.float32) / 255.0, (5, 5), 1.5)
    alpha = np.expand_dims(feathered, axis=2)

    blended = roi_orig * (1.0 - alpha) + roi_inp * alpha
    target_img[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)


def _get_affine_points(cx: float, cy: float, bw: int, bh: int, rot: float) -> Tuple[np.ndarray, np.ndarray]:
    rad = math.radians(rot)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    src_pts = np.float32([
        [cx - (bw / 2.0) * cos_a - (-bh / 2.0) * sin_a, cy + (-bw / 2.0) * sin_a + (-bh / 2.0) * cos_a],
        [cx + (bw / 2.0) * cos_a - (-bh / 2.0) * sin_a, cy + (bw / 2.0) * sin_a + (-bh / 2.0) * cos_a],
        [cx - (bw / 2.0) * cos_a - (bh / 2.0) * sin_a,  cy + (-bw / 2.0) * sin_a + (bh / 2.0) * cos_a]
    ])
    dst_pts = np.float32([[0, 0], [bw, 0], [0, bh]])
    return src_pts, dst_pts


def _blend_rotated_patch(
    image_np: np.ndarray,
    cleaned_upright: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    bw: int,
    bh: int,
    shape: str = "rect",
    mask_patch: Optional[np.ndarray] = None,
):
    img_h, img_w = image_np.shape[:2]
    ellipse_5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    if mask_patch is None:
        # Сплошная маска (white): эрозия убирает резкую прямоугольную кромку патча,
        # а BORDER_CONSTANT не даёт размытию «затянуть» внешнюю область внутрь.
        mask_patch = _create_shape_mask(bh, bw, shape)
        # Крошечный бабл (≤10px) эрозия съедала в ноль — тогда маску не трогаем.
        if bw > 10 and bh > 10:
            mask_patch = cv2.erode(mask_patch, ellipse_5, iterations=1)
    else:
        # Маска штрихов: дилатация компенсирует последующее размытие и не оставляет
        # полупрозрачный ореол старой буквы после обратного поворота.
        mask_patch = cv2.dilate(mask_patch, ellipse_5, iterations=1)

    mask_patch_feathered = cv2.GaussianBlur(
        mask_patch.astype(np.float32) / 255.0,
        (5, 5),
        1.2,
        borderType=cv2.BORDER_CONSTANT,
    )

    # Локальный ROI вместо полноэкранного warpAffine: раньше на каждый
    # повёрнутый бабл аллоцировались два массива размером со всю страницу
    # (~200-350 МБ на 4K-скан). Теперь обрабатываем только bbox повёрнутой рамки.
    src = src_pts.astype(np.float32)
    # src_pts = TL, TR, BL; четвёртый угол параллелограмма — BR = TR + BL - TL.
    fourth = src[1] + src[2] - src[0]
    quad = np.array([src[0], src[1], src[2], fourth], dtype=np.float32)

    pad = 2
    bx1 = max(0, int(math.floor(float(quad[:, 0].min()))) - pad)
    by1 = max(0, int(math.floor(float(quad[:, 1].min()))) - pad)
    bx2 = min(img_w, int(math.ceil(float(quad[:, 0].max()))) + pad)
    by2 = min(img_h, int(math.ceil(float(quad[:, 1].max()))) + pad)
    if bx2 <= bx1 or by2 <= by1:
        return

    roi_w, roi_h = bx2 - bx1, by2 - by1

    # warpAffine трактует матрицу как forward (patch -> страница) и сам её
    # инвертирует. Переносим целевую страницу к началу ROI, чтобы получить
    # координаты локального вывода.
    local_src = src - np.float32([bx1, by1])
    m_paste = cv2.getAffineTransform(dst_pts, local_src)
    cleaned_back = cv2.warpAffine(
        cleaned_upright, m_paste, (roi_w, roi_h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    alpha_back = cv2.warpAffine(
        mask_patch_feathered, m_paste, (roi_w, roi_h),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )

    roi = image_np[by1:by2, bx1:bx2].astype(np.float32)
    alpha_3d = np.expand_dims(alpha_back, axis=2)
    blended = roi * (1.0 - alpha_3d) + cleaned_back.astype(np.float32) * alpha_3d
    image_np[by1:by2, bx1:bx2] = np.clip(blended, 0, 255).astype(np.uint8)
